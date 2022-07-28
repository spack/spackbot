import os

import aiohttp
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


class WorkQueue:
    def __init__(self):
        logger.info(f"WorkQueue creating redis connection ({REDIS_HOST}, {REDIS_PORT})")
        self.redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
        # Name of queue workers use is defined in "workers/entrypoint.sh"
        self.task_q = Queue(name="tasks", connection=self.redis_conn)

    def get_queue(self):
        return self.task_q


work_queue = WorkQueue()


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "nothing to commit" in output


def report_style_failure(job, connection, type, value, traceback):
    """
    Get the api token from the job metadata, use it to post a comment on
    the PR containing the excepttion encountered and stack trace.

    """
    user_msg = comments.get_style_error_message(type, value, traceback)

    token = None
    if "token" in job.meta:
        token = job.meta["token"]

    url = job.meta["post_comments_url"]
    data = {"body": user_msg}

    helpers.synchronous_http_request(url, data=data, token=token)
    logger.error(user_msg)


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

            message += "\n\nI've updated the branch with isort fixes."

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
