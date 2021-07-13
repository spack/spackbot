# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging
import os
import random
import re
import requests

from sh.contrib import git
from .helpers import found, temp_dir, run_command
from gidgethub import routing


logger = logging.getLogger(__name__)
router = routing.Router()

# Aliases for spackbot so spackbot doesn't respond to himself
aliases = ["spack-bot", "spackbot", "spack-bot-develop"]
alias_regex = "(%s)" "|".join(aliases)


def say_hello():
    """
    Respond to saying hello.
    """
    messages = [
        "Hello!",
        "Hi! How are you?",
        "👋️",
        "Hola!",
        "Hey there!",
        "Howdy!",
        "こんにちは！",
    ]
    return random.choice(messages)


commands_message = """
You can interact with me in many ways! 

- `@spackbot hello`: say hello and get a friendly response back!
- `@spackbot help` or `@spackbot commands`: see this message 
- `@spackbot fix style`: ask me to fix a failed style check

I'll also help to label your pull request and assign reviewers!
If you need help or see there might be an issue with me, open an issue [here](https://github.com/spack/spack-bot/issues)
"""


def get_style_message(output):
    """
    Given a terminal output, wrap in a message
    """
    return (
        """
I was able to run `spack style --fix` for you!
    
```bash
%s
```    
Keep in mind that I cannot fix your flake8 or mypy errors, so if you have any you'll need to fix them and update the pull request."""
        % output
    )


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "branch is up to date" in output


async def fix_style(event, gh, token):
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
    if not await found(gh.getitem(collaborators_url, {"collaborator": sender})):
        logger.info(f"Not found: {sender}")
        return (
            "Sorry %s, I cannot do that for you. Only users with write can make this request!"
            % sender
        )

    # Tell the user the style fix is going to take a minute or two
    message = "Let me see if I can fix that for you! This might take a moment..."
    await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})

    # Get the username of the original committer
    user = pr["user"]["login"]
    email = "%s@users.noreply.github.com" % user

    # Get the branch and pull request url
    branch = pr["head"]["ref"]
    clone_url = pr["head"]["repo"]["svn_url"]
    naked_url = clone_url.replace("https://", "", 1)

    # If for some reason the message below isn't generated?
    message = "There was a problem running fixes! @spackbot needs a maintainer's help!"

    # At this point, we can clone the repository and make the change
    with temp_dir() as cwd:
        git("clone", "-b", branch, clone_url)
        os.chdir("spack")
        git("config", "--local", "user.name", user)
        git("config", "--local", "user.email", email)

        # This will authenticate the push with the app token
        git(
            "remote",
            "set-url",
            "origin",
            "https://%s:%s@%s.git" % (user, token, naked_url),
        )

        # We need to add develop remote for this to work
        git("remote", "add", "upstream", "https://github.com/spack/spack")
        git("fetch", "upstream")

        # This won't work if we are already on a develop branch
        if branch != "develop":
            git("checkout", "--track", "upstream/develop")
            git("checkout", branch)

        # Add newly cloned `spack` to PATH
        os.environ["PATH"] = f"{cwd}/spack/bin:" + os.environ["PATH"]
        from sh import spack

        # Save the message for the user
        res, err = run_command(spack, ["--color", "never", "style", "--fix"])

        # If the branch is really old and there is no style command
        if "Unknown command" in err:
            return "It looks like your branch is too old to have spack style! Please update it and try again."
        message = get_style_message(res)

        # Commit (allow for no changes)
        res, err = run_command(
            git,
            ["commit", "-a", "-m", "[spackbot] updating style on behalf of %s" % user],
        )

        # Continue differently if the branch is up to date or not
        if is_up_to_date(res):
            message += "\nI wasn't able to make any changes, but please see the message above for any remaining issues!"
            return message
        message += "\nI've updated the branch with isort fixes."

        # Finally, try to push, update the message if permission not allowed
        try:
            git("push", "origin", branch)
        except:
            message += "\n\nBut it looks like I'm not able to push to your branch. 😭️"

    return message


@router.register("issue_comment", action="created")
@router.register("issue_comment", action="edited")
async def add_comments(event, gh, *args, session, **kwargs):
    """
    Respond to messages (comments) to spackbot
    """
    # We can only tell PR and issue comments apart by this field
    if "pull_request" not in event.data["issue"]:
        return

    # spackbot should not respond to himself!
    if re.search(alias_regex, event.data["comment"]["user"]["login"]):
        return

    # Respond with appropriate messages
    comment = event.data["comment"]["body"]

    # @spackbot hello
    message = None
    if re.search("@spackbot hello", comment, re.IGNORECASE):
        logger.info(f"Responding to hello message {comment}...")
        message = say_hello()

    # @spackbot commands OR @spackbot help
    elif re.search("@spackbot (commands|help)", comment, re.IGNORECASE):
        logger.debug("Responding to request for help commands.")
        message = commands_message

    elif re.search("@spackbot fix style", comment, re.IGNORECASE):
        logger.debug("Responding to request to fix style")
        token = kwargs.get("token")
        message = await fix_style(event, gh, token)

    if message:
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})
