# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import urllib.parse

import aiohttp
import boto3
from datetime import datetime
from gidgethub import aiohttp as gh_aiohttp
import re

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
TASK_QUEUE_SHORT = os.environ.get("TASK_QUEUE_SHORT", "tasks")
TASK_QUEUE_LONG = os.environ.get("TASK_QUEUE_LONG", "tasks_long")
QUERY_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# If we don't provide a timeout, the default in RQ is 180 seconds
WORKER_JOB_TIMEOUT = int(os.environ.get("WORKER_JOB_TIMEOUT", "21600"))

# We can only make the pipeline request with a GITLAB TOKEN
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")

redis = Redis(host=REDIS_HOST, port=REDIS_PORT)

allow_edits_url = (
    "https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/"
    "allowing-changes-to-a-pull-request-branch-created-from-a-fork"
    "#enabling-repository-maintainer-permissions-on-existing-pull-requests"
)


def get_queue(name):
    return Queue(name=name, connection=redis)


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "nothing to commit" in output


async def check_gitlab_has_latest(branch_name, pr_head_sha, gh, comments_url):
    """
    Given the name of the branch supposedly pushed to gitlab, check if it
    is the latest revision found on github.  If gitlab doesn't have the
    latest, the pipeline cannot be run, so post a comment on the PR to
    explain why, if that is the case.

    Arguments:
        branch_name (str): Name of branch to query on GitLab for latest commit
        pr_head_sha (str): SHA of PR head from GitHub
        gh: GitHubAPI object for posting comments on the PR
        comments_url (str): URL to post any error message to

    Returns: True if gitlab has the latest revsion, False otherwise.
    """
    # Get the commit for the PR branch from GitLab to see what's been pushed there
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    commit_url = f"{helpers.gitlab_spack_project_url}/repository/commits/{branch_name}"
    gitlab_commit = await helpers.get(commit_url, headers)

    error_msg = comments.cannot_run_pipeline_comment

    if not gitlab_commit or "parent_ids" not in gitlab_commit:
        details = f"Unexpected response from gitlab: {gitlab_commit}"
        logger.debug(f"Problem with {branch_name}: {details}")
        msg = comments.format_generic_details_msg(error_msg, details)
        await gh.post(comments_url, {}, data={"body": msg})
        return False

    parent_ids = gitlab_commit["parent_ids"]

    if pr_head_sha not in parent_ids:
        pids = [pid[:7] for pid in parent_ids]
        details = f"pr head: {pr_head_sha[:7]}, gitlab commit parents: {pids}"
        logger.debug(f"Problem with {branch_name}: {details}")
        msg = comments.format_generic_details_msg(error_msg, details)
        await gh.post(comments_url, {}, data={"body": msg})
        return False

    return True


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


def report_pipeline_failure(job, connection, type, value, traceback):
    user_msg = comments.format_error_message(
        "I encountered an error attempting to run the pipeline.",
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

        comments_url = event.data["issue"]["comments_url"]

        # Early exit if not authenticated
        if not GITLAB_TOKEN:
            msg = "I'm not able to run the pipeline now because I don't have authentication."
            await gh.post(comments_url, {}, data={"body": msg})
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
            await gh.post(comments_url, {}, data={"body": msg})
            return

        # We need the branch name plus number to assemble the GitLab CI api requests
        branch = pr["head"]["ref"]
        pr_mirror_key = f"pr{number}_{branch}"
        branch = urllib.parse.quote_plus(pr_mirror_key)

        # If gitlab doesn't have the latest PR head sha from GitHub, we can't run the
        # pipeline.
        head_sha = pr["head"]["sha"]
        if not await check_gitlab_has_latest(branch, head_sha, gh, comments_url):
            return

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
            mirror_template = urllib.parse.quote_plus("single-src-pr-mirrors.yaml.in")
            url = f"{url}&variables[][key]=PIPELINE_MIRROR_TEMPLATE&variables[][value]={mirror_template}"

            logger.info(
                f"Deleting {helpers.pr_mirror_base_url}/{pr_mirror_key} for rebuild request by {sender}"
            )

            pr_url = helpers.s3_parse_url(
                f"{helpers.pr_mirror_base_url}/{pr_mirror_key}"
            )
            # Wipe out PR binary mirror contents
            s3 = boto3.resource("s3")
            bucket = s3.Bucket(pr_url.get("bucket"))
            bucket.objects.filter(Prefix=pr_url.get("prefix")).delete()

        # Use helpers.post because it creates a new session (and here we are
        # communicating with gitlab rather than github).
        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        logger.info(f"{sender} triggering pipeline, url = {url}")
        result = await helpers.post(url, headers)

        detailed_status = result.get("detailed_status", {})
        if "details_path" in detailed_status:
            url = urllib.parse.urljoin(
                helpers.spack_gitlab_url, detailed_status["details_path"]
            )
            logger.info(f"Triggering pipeline on {branch}: {url}")
            msg = f"I've started that [pipeline]({url}) for you!"
            await gh.post(comments_url, {}, data={"body": msg})
        else:
            logger.info(f"Problem triggering pipeline on {branch}")
            logger.info(result)
            msg = "I had a problem triggering the pipeline."
            await gh.post(comments_url, {}, data={"body": msg})


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
                message += (
                    f"\n\nBut it looks like I'm not able to push to your branch. 😭️"
                    f" Did you check [Allow edits from maintainers]({allow_edits_url})"
                    f" when you opened the PR?"
                )

            await gh.post(
                event.data["issue"]["comments_url"], {}, data={"body": message}
            )


async def copy_pr_mirror(pr_mirror_url, shared_pr_mirror_url):
    """Copy between the S3 per-pr mirror and the shared pr mirror.

    Parameters:
        pr_mirror_url        (string): URL to S3 mirror for a PR
        shared_pr_mirror_url (string): URL to S3 mirror for shared PR binaries
    """
    pr_url = helpers.s3_parse_url(pr_mirror_url)
    shared_pr_url = helpers.s3_parse_url(shared_pr_mirror_url)

    s3 = boto3.resource("s3")
    pr_bucket_name = pr_url.get("bucket")
    pr_bucket = s3.Bucket(pr_bucket_name)
    pr_mirror_prefix = pr_url.get("prefix")

    shared_pr_bucket = s3.Bucket(shared_pr_url.get("bucket"))
    shared_pr_mirror_prefix = shared_pr_url.get("prefix")

    # Files extensions to copy
    extensions = (".spack", ".spec.json", ".spec.yaml", ".spec.json.sig")

    for obj in pr_bucket.objects.filter(Prefix=pr_mirror_prefix):
        if obj.key.endswith(extensions):
            # Create a new opject replacing the first instance of the pr_mirror_prefix
            # with the shared_pr_mirror_prefix.
            new_obj = shared_pr_bucket.Object(
                obj.key.replace(pr_mirror_prefix, shared_pr_mirror_prefix, 1)
            )
            # Copy the PR mirror object to the new object in the shared PR mirror
            new_obj.copy(
                {
                    "Bucket": pr_bucket_name,
                    "Key": obj.key,
                }
            )


async def delete_pr_mirror(pr_mirror_url):
    """Delete a mirror from S3. This routine was written for PR mirrors
    but is general enough to be used to delete any S3 mirror.

        Parameters:
            pr_mirror_url (string): URL to S3 mirror
    """
    pr_url = helpers.s3_parse_url(pr_mirror_url)

    s3 = boto3.resource("s3")
    pr_bucket = s3.Bucket(pr_url.get("bucket"))
    pr_mirror_prefix = pr_url.get("prefix")
    pr_bucket.objects.filter(Prefix=pr_mirror_prefix).delete()


def list_ci_stacks(spack_root):
    """Loop through the CI stacks in the spack repo.

    Parameters:
        spack_root (path): Root of a spack clone
    """
    pipeline_root = f"{spack_root}/share/spack/gitlab/cloud_pipelines/stacks/"
    for stack in os.listdir(pipeline_root):
        if os.path.isfile(f"{pipeline_root}/{stack}/spack.yaml"):
            yield stack


def hash_from_key(key):
    """This works because we guarentee the hash is in the key string.
    If this assumption is ever broken, this code will break.

        Parameters:
            key (string): File/Object name that contains a spack package concrete
                          hash.
    """
    h = None
    # hash is 32 chars long between a "-" and a "."
    # examples include:
    # linux-ubuntu18.04-x86_64-gcc-8.4.0-armadillo-10.5.0-gq3ijjrtnzgpm4bvuamjr6wa7hzxkypz.spack
    # linux-ubuntu18.04-x86_64-gcc-8.4.0-armadillo-10.5.0-gq3ijjrtnzgpm4bvuamjr6wa7hzxkypz.spec.json
    h = re.findall(r"-([a-zA-Z0-9]{32,32})\.", key.lower())
    if len(h) > 1:
        # Error, multiple matches are ambigious
        h = None
    elif h:
        h = h[0]
    return h


def check_skip_job(job=None):
    """Check if there is another job in the queue that is of the same type.

    Parameters:
        job (rq.Job): Job to check (default=rq.get_current_job)
    """

    if not job:
        job = get_current_job()

    job_type = job.meta.get("type", "-")
    skip = False
    logger.debug(f"-- Checking skip job({job.id}): {job_type}")
    # Check if another job of this type is queued
    queue = get_queue(job.origin)
    for _job in queue.jobs:
        _job_type = _job.meta["type"]
        logger.debug(f"-- job({_job.id}): {_job_type}")
        if _job.meta["type"] == job_type:
            skip = True
            break

    if skip:
        logger.debug(f"Skipping {job_type} job")
        pr_number = job.meta.get("pr_number", None)
        if pr_number:
            logger.debug(f"PR: https://github.com/spack/spack/pull/{pr_number}")

    return skip


# Prune per stack mirror
async def prune_mirror_duplicates(shared_pr_mirror_url, publish_mirror_url):
    """Prune objects from the S3 mirror for shared PR binaries that have been published to the
    develop mirror or have expired.

        Parameters:
            shared_pr_mirror_url (string): URL to S3 mirror for shared PR binaries
            publish_mirror_url   (string): URL to S3 mirror for published PR binaries
    """

    # Current job stack
    if check_skip_job():
        return

    s3 = boto3.resource("s3")

    with helpers.temp_dir() as cwd:
        git.clone(
            "--branch",
            helpers.pr_expected_base,
            "--depth",
            1,
            helpers.spack_upstream,
            "spack",
        )

        for stack in list_ci_stacks(f"{cwd}/spack"):
            shared_pr_url = helpers.s3_parse_url(
                shared_pr_mirror_url.format_map({"stack": stack})
            )
            shared_pr_bucket_name = shared_pr_url.get("bucket")
            shared_pr_bucket = s3.Bucket(shared_pr_bucket_name)
            shared_pr_mirror_prefix = shared_pr_url.get("prefix")

            publish_url = helpers.s3_parse_url(
                publish_mirror_url.format_map({"stack": stack})
            )
            publish_bucket = s3.Bucket(publish_url.get("bucket"))
            publish_mirror_prefix = publish_url.get("prefix")

            # All of the expected possible spec file extensions
            extensions = (".spec.json", ".spec.yaml", ".spec.json.sig")

            # Get the current time for age based pruning
            now = datetime.now()
            delete_specs = set()
            shared_pr_specs = set()
            for obj in shared_pr_bucket.objects.filter(
                Prefix=shared_pr_mirror_prefix,
            ):
                # Need to convert from aware to naive time to get delta
                last_modified = obj.last_modified.replace(tzinfo=None)
                # Prune obj.last_modified > helpers.shared_pr_mirror_retire_after_days
                # (default: 7) days to avoid storing cached objects that only
                # existed during development.
                # Anything older than the retirement age should just be indesciminately
                # pruned
                if (
                    now - last_modified
                ).days >= helpers.shared_pr_mirror_retire_after_days:
                    logger.debug(
                        f"pr mirror pruning {obj.key} from s3://{shared_pr_bucket_name}: "
                        "reason(age)"
                    )
                    obj.delete()

                    # Grab the hash from the object, to ensure all of the files associated with
                    # it are also removed.
                    spec_hash = hash_from_key(obj.key)
                    if spec_hash:
                        delete_specs.add(spec_hash)
                    continue

                if not obj.key.endswith(extensions):
                    continue

                # Get the hashes in the shared PR bucket.
                spec_hash = hash_from_key(obj.key)
                if spec_hash:
                    shared_pr_specs.add(spec_hash)
                else:
                    logger.error(
                        f"Encountered spec file without hash in name: {obj.key}"
                    )

            # Check in the published base branch bucket for duplicates to delete
            for obj in publish_bucket.objects.filter(
                Prefix=publish_mirror_prefix,
            ):
                if not obj.key.endswith(extensions):
                    continue

                spec_hash = hash_from_key(obj.key.lower())
                if spec_hash in shared_pr_specs:
                    delete_specs.add(spec_hash)

            # Also look at the .spack files for deletion
            extensions = (".spack", *extensions)

            # Delete all of the objects with marked hashes
            for obj in shared_pr_bucket.objects.filter(
                Prefix=shared_pr_mirror_prefix,
            ):
                if not obj.key.endswith(extensions):
                    continue

                if hash_from_key(obj.key) in delete_specs:
                    logger.debug(
                        f"pr mirror pruning {obj.key} from s3://{shared_pr_bucket_name}: "
                        "reason(published)"
                    )
                    obj.delete()


# Upate index per stack mirror
async def update_mirror_index(base_mirror_url):
    """Use spack buildcache command to update index for each Spack CI stack mirror.

    Parameters:
        base_mirror_url (string): Base URL to S3 mirror with the format placeholder {stack}
                             where the stack name will go in the URL.
    """

    # Current job stack
    if check_skip_job():
        return

    with helpers.temp_dir() as cwd:
        git.clone(
            "--branch",
            helpers.pr_expected_base,
            "--depth",
            1,
            helpers.spack_upstream,
            "spack",
        )
        spack = sh.Command(f"{cwd}/spack/bin/spack")

        for stack in list_ci_stacks(f"{cwd}/spack"):
            stack_mirror_url = base_mirror_url.format_map({"stack": stack})
            print(f"Updating binary index at {stack_mirror_url}")
            helpers.run_command(
                spack,
                [
                    "-d",
                    "buildcache",
                    "update-index",
                    f"{stack_mirror_url}",
                ],
            )
