# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import io
import logging
import os
import sh

from sh.contrib import git

import spackbot.comments as comments
import spackbot.helpers as helpers


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


def get_style_message(output):
    """Given a terminal output, wrap in a message."""
    # The output is limited to what GitHub can store in comments,
    # 65,536 4-byte unicode total rounded down -300 for text below
    if len(output) >= 64700:
        output = output[:64682] + "\n... truncated ..."

    return f"""
I was able to run `spack style --fix` for you!
<details>
<summary><b>spack style --fix</b></summary>

```bash
{output}
```
</details>
"""


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
    pr = await gh.getitem(event.data["issue"]["pull_request"]["url"])

    # Get the sender of the PR - do they have write?
    sender = event.data["sender"]["login"]
    repository = event.data["repository"]
    collaborators_url = repository["collaborators_url"]

    # If they don't have write, we don't allow the command
    if not await helpers.found(gh.getitem(collaborators_url, {"collaborator": sender})):
        logger.info(f"Will not fix changes for user without write access: {sender}")
        return (
            f"Sorry {sender}, I cannot do that for you. "
            f"Only users with write can make this request!"
        )

    # Tell the user the style fix is going to take a minute or two
    message = "Let me see if I can fix that for you! This might take a moment..."
    await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})

    # Get the username of the original committer
    user = pr["user"]["login"]

    # We need the user id if the user is before July 18. 2017
    email = await helpers.get_user_email(gh, user)

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

        # run spack style
        out = io.StringIO()
        errors = False
        try:
            spack("--color", "never", "style", "--fix", _out=out)
            logger.debug("spack style found no errors.")
        except sh.ErrorReturnCode:
            logger.debug("spack style was unable to fix all errors.")
            errors = True

        # format the output in a message (output is in out even if there is an error)
        message = io.StringIO(get_style_message(out.getvalue()))

        # figure out if `spack style --fix` changed anything
        changes = False
        try:
            git.diff("--quiet")
            logger.debug("git diff found no changes")
        except sh.ErrorReturnCode:
            logger.debug("git diff found changes")
            changes = True

        # just stop here if there is nothing to be done.
        if not changes and not errors:
            message.write("Your code looks great! There's nothing to fix.\n")
            return message.getvalue()

        # try to commit and push any changes
        if changes:
            howmany = "some" if errors else "all"
            message.write(f"I was able to fix {howmany} of the errors in your code!\n")

            try:
                logger.debug("committing changes.")
                git.commit("-am", f"[spackbot] update style on behalf of {user}")
                git.push("origin", branch)
                message.write("I've pushed a commit with the changes.\n")

            except sh.ErrorReturnCode as code:
                logger.debug(f"git commit return an error: {code}")
                message.write(
                    "\n\nIt looks like I'm not able to push to your branch. 😭 "
                    "Did you [enable repository maintainer permissions]"
                    "(https://docs.github.com/en/github/"
                    "collaborating-with-pull-requests/working-with-forks/"
                    "allowing-changes-to-a-pull-request-branch-created-from-a-fork) "
                    "for this PR?\n"
                )

        if errors:
            message.write(
                "\n\nThere are some errors that I couldn't fix, so you'll "
                "need to fix them and update the pull request. "
                "See the output above for details.\n"
            )

    return message.getvalue()
