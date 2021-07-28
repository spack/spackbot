# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import spackbot.comments as comments
import spackbot.helpers as helpers
from sh.contrib import git
import requests
import logging
import os
import sh

logger = logging.getLogger(__name__)


async def style_comment(event, gh):
    """
    Make a comment on how to fix style
    """
    # If we get here, we have a style failure
    # Find the pull request that is matched to the repository. It looks like
    # checks are shared across different repos (e.g., a fork and upstream)
    repository = event.data["repository"]["full_name"]
    for pr in event.data["check_run"]["pull_requests"]:
        if repository in pr["url"]:

            number = pr["url"].split("/")[-1]
            comments_url = (
                f"https://api.github.com/repos/{repository}/issues/{number}/comments"
            )
            await gh.post(comments_url, {}, data={"body": comments.style_message})


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "branch is up to date" in output


async def fix_style(event, gh):
    """
    Respond to a request to fix style.
    We first retrieve metadata about the pull request. If the request comes
    from anyone with write access to the repository, we commit, and we commit
    under the identity of the original person that opened the PR.
    """
    response = requests.get(event.data["issue"]["pull_request"]["url"])
    pr = response.json()

    # Get the sender of the PR - do they have write?
    sender = event.data["sender"]["login"]
    repository = event.data["repository"]
    collaborators_url = repository["collaborators_url"]

    # If they don't have write, we don't allow the command
    if not await helpers.found(gh.getitem(collaborators_url, {"collaborator": sender})):
        logger.info(f"Not found: {sender}")
        return f"Sorry {sender}, I cannot do that for you. Only users with write can make this request!"

    # Tell the user the style fix is going to take a minute or two
    message = "Let me see if I can fix that for you! This might take a moment..."
    await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})

    # Get the username of the original committer
    user = pr["user"]["login"]

    # We need the user id if the user is before July 18. 2017
    email = helpers.get_user_email(user)

    # We need to use the git url with ssh
    branch = pr["head"]["ref"]
    full_name = pr["head"]["repo"]["full_name"]
    fork_url = f"git@github.com:{full_name}.git"

    # At this point, we can clone the repository and make the change
    with helpers.temp_dir() as cwd:

        # Clone a fresh spack develop to use for spack style
        git("clone", helpers.spack_upstream, "spack-develop")

        spack = sh.Command(f"{cwd}/spack-develop/bin/spack")

        # clone the develop repository to another folder for our PR
        git("clone", "spack-develop", "spack")

        os.chdir("spack")
        git("config", "user.name", user)
        git("config", "user.email", email)

        # This will authenticate the push with the added ssh credentials
        git("remote", "add", "upstream", helpers.spack_upstream)
        git("remote", "set-url", "origin", fork_url)

        # we're on upstream/develop. Fetch and check out just the PR branch
        git("fetch", "origin", f"{branch}:{branch}")
        git("checkout", branch)

        # Save the message for the user
        res, err = helpers.run_command(spack, ["--color", "never", "style", "--fix"])
        message = comments.get_style_message(res)

        # Commit (allow for no changes)
        res, err = helpers.run_command(
            git,
            ["commit", "-a", "-m", f"[spackbot] updating style on behalf of {user}"],
        )

        # Continue differently if the branch is up to date or not
        if is_up_to_date(res):
            message += "\nI wasn't able to make any further changes, but please see the message above for remaining issues you can fix locally!"
            return message
        message += "\nI've updated the branch with isort fixes."

        # Finally, try to push, update the message if permission not allowed
        try:
            git("push", "origin", branch)
        except Exception:
            message += "\n\nBut it looks like I'm not able to push to your branch. 😭️ Did you check maintainer can edit when you opened the PR?"

    return message
