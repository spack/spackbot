# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import urllib.parse

import aiohttp
import boto3
from gidgethub import aiohttp as gh_aiohttp
from sh.contrib import git
import sh

from redis import Redis
from rq import get_current_job, Queue


import spackbot.comments as comments
import spackbot.helpers as helpers
from .auth import REQUESTER

logger = helpers.get_logger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TASK_QUEUE_NAME = os.environ.get("TASK_QUEUE_NAME", "tasks")

# If we don't provide a timeout, the default in RQ is 180 seconds
WORKER_JOB_TIMEOUT = int(os.environ.get("WORKER_JOB_TIMEOUT", "21600"))

# We can only make the pipeline request with a GITLAB TOKEN
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")


class WorkQueue:
    def __init__(self):
        logger.info(f"WorkQueue creating redis connection ({REDIS_HOST}, {REDIS_PORT})")
        self.redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
        # Name of queue workers use is defined in "workers/entrypoint.sh"
        self.task_q = Queue(name=TASK_QUEUE_NAME, connection=self.redis_conn)

    def get_queue(self):
        return self.task_q


work_queue = WorkQueue()


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "nothing to commit" in output


def post_failure_message(job, msg):
    """
    Get the api token from the job metadata, use it to post a comment on
    the PR containing the excepttion encountered and stack trace.

    """
    token = None
    if "token" in job.meta:
        token = job.meta["token"]

    url = job.meta["post_comments_url"]
    data = {"body": msg}

    helpers.synchronous_http_request(url, data=data, token=token)
    logger.error(msg)


def report_style_failure(job, connection, type, value, traceback):
    user_msg = comments.format_error_message(
        "I encountered an error attempting to format style.", type, value, traceback
    )
    post_failure_message(job, user_msg)


def report_rebuild_failure(job, connection, type, value, traceback):
    user_msg = comments.format_error_message(
        "I encountered an error attempting to rebuild everything.",
        type,
        value,
        traceback,
    )
    post_failure_message(job, user_msg)


async def run_pipeline_task(event):
    """
    Send an api request to gitlab telling it to run a pipeline on the
    PR branch for the associated PR.  If the job metadata includes the
    "rebuild_everything" key set to True, then this method will take the
    extra couple steps to trigger a pipeline that will rebuild all specs
    from source.  This involves clearing the dedicated mirror for the
    associated PR, and setting the "SPACK_PRUNE_UNTOUCHED" env var to
    False (so that pipeline generation doesn't trim jobs for specs it
    thinks aren't touched by the PR).
    """
    job = get_current_job()
    token = job.meta["token"]
    rebuild_everything = job.meta.get("rebuild_everything")

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, REQUESTER, oauth_token=token)

        # Early exit if not authenticated
        if not GITLAB_TOKEN:
            msg = "I'm not able to rebuild everything now because I don't have authentication."
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})
            return

        # Get the pull request number
        pr_url = event.data["issue"]["pull_request"]["url"]
        *_, number = pr_url.split("/")

        # We need the pull request branch
        pr = await gh.getitem(pr_url)

        # Get the sender of the PR - do they have write?
        sender = event.data["sender"]["login"]
        repository = event.data["repository"]
        collaborators_url = repository["collaborators_url"]
        author = pr["user"]["login"]

        # If it's the PR author, we allow it
        if author == sender:
            logger.info(
                f"Author {author} of PR #{number} is requesting a pipeline run."
            )

        # If they don't have write, we don't allow the command
        elif not await helpers.found(
            gh.getitem(collaborators_url, {"collaborator": sender})
        ):
            logger.info(f"Not found: {sender}")
            msg = f"Sorry {sender}, I cannot do that for you. Only users with write can make this request!"
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})
            return

        # We need the branch name plus number to assemble the GitLab CI
        branch = pr["head"]["ref"]
        pr_mirror_key = f"pr{number}_{branch}"
        branch = urllib.parse.quote_plus(pr_mirror_key)

        url = f"{helpers.gitlab_spack_project_url}/pipeline?ref={branch}"

        if rebuild_everything:
            # Rebuild everything is accomplished by telling spack pipeline generation
            # not to do any of the normal pruning (DAG pruning, untouched spec pruning).
            # But we also wipe out the contents of the PR-specific mirror.  See docs on
            # use of variables:
            #
            #    https://docs.gitlab.com/ee/api/index.html#array-of-hashes
            #
            # Also see issue contradicting the docs:
            #
            #    https://gitlab.com/gitlab-org/gitlab/-/issues/23394
            #
            url = (
                f"{url}&variables[][key]=SPACK_PRUNE_UNTOUCHED&variables[][value]=False"
            )
            url = f"{url}&variables[][key]=SPACK_PRUNE_UP_TO_DATE&variables[][value]=False"

            logger.info(
                f"Deleting s3://{helpers.pr_mirror_bucket}/{pr_mirror_key} for rebuild request by {sender}"
            )

            # Wipe out PR binary mirror contents
            s3 = boto3.resource("s3")
            bucket = s3.Bucket(helpers.pr_mirror_bucket)
            bucket.objects.filter(Prefix=pr_mirror_key).delete()

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

        # Use helpers.post because it creates a new session (and here we are
        # communicating with gitlab rather than github).
        logger.info(f"{sender} triggering pipeline, url = {url}")
        result = await helpers.post(url, headers)

        detailed_status = result.get("detailed_status", {})
        if "details_path" in detailed_status:
            url = f"{helpers.spack_gitlab_url}/{detailed_status['details_path']}"
            logger.info(f"Triggering pipeline on {branch}: {url}")
            msg = f"I've started that [pipeline]({url}) for you!"
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})
        else:
            logger.info(f"Problem triggering pipeline on {branch}")
            logger.info(result)
            msg = "I had a problem triggering the pipeline."
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})


async def fix_style_task(event):
    """
    We first retrieve metadata about the pull request. If the request comes
    from anyone with write access to the repository, we commit, and we commit
    under the identity of the original person that opened the PR.
    """
    job = get_current_job()
    token = job.meta["token"]

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, REQUESTER, oauth_token=token)

        pr_url = event.data["issue"]["pull_request"]["url"]

        pr = await gh.getitem(pr_url)

        logger.debug("GitHub PR")
        logger.debug(pr)

        # Get the sender of the PR - do they have write?
        sender = event.data["sender"]["login"]
        repository = event.data["repository"]
        collaborators_url = repository["collaborators_url"]
        author = pr["user"]["login"]

        logger.debug(
            f"sender = {sender}, repo = {repository}, collabs_url = {collaborators_url}"
        )

        # If they didn't create the PR and don't have write, we don't allow the command
        if sender != author and not await helpers.found(
            gh.getitem(collaborators_url, {"collaborator": sender})
        ):
            msg = f"Sorry {sender}, I cannot do that for you. Only {author} and users with write can make this request!"
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})
            return

        # Tell the user the style fix is going to take a minute or two
        message = "Let me see if I can fix that for you!"
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})

        # Get the username of the original committer
        user = pr["user"]["login"]

        # We need the user id if the user is before July 18, 2017.  See note about why
        # here:
        #
        #     https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email-address
        #
        email = await helpers.get_user_email(gh, user)

        # We need to use the git url with ssh
        remote_branch = pr["head"]["ref"]
        local_branch = "spackbot-style-check-working-branch"
        full_name = pr["head"]["repo"]["full_name"]
        fork_url = f"git@github.com:{full_name}.git"

        logger.info(
            f"fix_style_task, user = {user}, email = {email}, fork = {fork_url}, branch = {remote_branch}\n"
        )

        # At this point, we can clone the repository and make the change
        with helpers.temp_dir() as cwd:

            # Clone a fresh spack develop to use for spack style
            git.clone(helpers.spack_upstream, "spack-develop")

            spack = sh.Command(f"{cwd}/spack-develop/bin/spack")

            # clone the develop repository to another folder for our PR
            git.clone("spack-develop", "spack")

            os.chdir("spack")

            git.config("user.name", user)
            git.config("user.email", email)

            # This will authenticate the push with the added ssh credentials
            git.remote("add", "upstream", helpers.spack_upstream)
            git.remote("set-url", "origin", fork_url)

            # we're on upstream/develop. Fetch just the PR branch
            helpers.run_command(
                git, ["fetch", "origin", f"{remote_branch}:{local_branch}"]
            )

            # check out the PR branch
            helpers.run_command(git, ["checkout", local_branch])

            # Run the style check and save the message for the user
            check_dir = os.getcwd()
            res, err = helpers.run_command(
                spack, ["--color", "never", "style", "--fix", "--root", check_dir]
            )
            logger.debug("spack style [output]")
            logger.debug(res)
            logger.debug("spack style [error]")
            logger.debug(err)

            message = comments.get_style_message(res)

            # Commit (allow for no changes)
            res, err = helpers.run_command(
                git,
                [
                    "commit",
                    "-a",
                    "-m",
                    f"[{helpers.botname}] updating style on behalf of {user}",
                ],
            )

            # Continue differently if the branch is up to date or not
            if is_up_to_date(res):
                logger.info("Unable to make any further changes")
                message += "\nI wasn't able to make any further changes, but please see the message above for remaining issues you can fix locally!"
                await gh.post(
                    event.data["issue"]["comments_url"], {}, data={"body": message}
                )
                return

            message += "\n\nI've updated the branch with style fixes."

            # Finally, try to push, update the message if permission not allowed
            try:
                helpers.run_command(
                    git, ["push", "origin", f"{local_branch}:{remote_branch}"]
                )
            except Exception:
                logger.error("Unable to push to branch")
                message += "\n\nBut it looks like I'm not able to push to your branch. 😭️ Did you check maintainer can edit when you opened the PR?"

            await gh.post(
                event.data["issue"]["comments_url"], {}, data={"body": message}
            )
