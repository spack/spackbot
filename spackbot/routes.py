# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import re

from gidgethub import sansio

# View handler functions
import spackbot.handlers as handlers
import spackbot.comments as comments
import spackbot.helpers as helpers

from gidgethub import routing
from typing import Any

logger = helpers.get_logger(__name__)


class SpackbotRouter(routing.Router):
    """
    Custom router to handle common interactions for spackbot
    """

    async def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event to all registered function(s)."""

        # if we haven't retrieved package list yet, do so
        if not hasattr(self, "packages"):
            self.packages = await helpers.list_packages()

        # for all endpoints, spackbot should not respond to himself!
        if "comment" in event.data and re.search(
            helpers.alias_regex, event.data["comment"]["user"]["login"]
        ):
            return

        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            await callback(event, *args, **kwargs)


router = SpackbotRouter()


@router.register("check_run", action="completed")
async def add_style_comments(event, gh, *args, session, **kwargs):
    """
    Respond to all check runs (e.g., for style or GitHub Actions)
    """
    # Nothing to do with success
    if event.data["check_run"]["conclusion"] == "success":
        return

    check_name = event.data["check_run"]["name"]
    logger.info(f"check run {check_name} unsuccesful")

    # If it's not a style check, we don't care
    if check_name == "style":
        await handlers.style_comment(event, gh)


@router.register("pull_request", action="opened")
async def on_pull_request(event, gh, *args, session, **kwargs):
    """
    Respond to the pull request being opened
    """
    await handlers.add_reviewers(event, gh)


@router.register("issue_comment", action="created")
async def add_comments(event, gh, *args, session, **kwargs):
    """
    Receive pull request comments
    """
    # We can only tell PR and issue comments apart by this field
    if "pull_request" not in event.data["issue"]:
        return

    # Respond with appropriate messages
    comment = event.data["comment"]["body"]

    # @spackbot hello
    message = None
    if re.search(f"{helpers.botname} hello", comment, re.IGNORECASE):
        logger.info(f"Responding to hello message {comment}...")
        message = comments.say_hello()

    # Hey @spackbot tell me a joke!
    elif helpers.botname in comment and "joke" in comment:
        logger.info(f"Responding to request for joke {comment}...")
        message = await comments.tell_joke(gh)

    elif re.search(f"{helpers.botname} fix style", comment, re.IGNORECASE):
        logger.debug("Responding to request to fix style")
        message = await handlers.fix_style(event, gh, *args, **kwargs)

    # @spackbot commands OR @spackbot help
    elif re.search(f"{helpers.botname} (commands|help)", comment, re.IGNORECASE):
        logger.debug("Responding to request for help commands.")
        message = comments.commands_message

    # @spackbot maintainers or @spackbot request review
    elif re.search(
        f"{helpers.botname} (maintainers|request review)", comment, re.IGNORECASE
    ):
        logger.debug("Responding to request to assign maintainers for review.")
        await handlers.add_reviewers(event, gh)

    # @spackbot run pipeline | @spackbot re-run pipeline
    elif re.search(f"{helpers.botname} (re-?)?run pipeline", comment, re.IGNORECASE):
        logger.info("Responding to request to re-run pipeline...")
        await handlers.run_pipeline(event, gh, **kwargs)

    # @spackbot rebuild everything
    elif re.search(f"{helpers.botname} rebuild everything", comment, re.IGNORECASE):
        logger.info("Responding to request to rebuild everthing...")
        await handlers.run_pipeline_rebuild_all(event, gh, **kwargs)

    if message:
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})


@router.register("pull_request", action="opened")
@router.register("pull_request", action="synchronize")
async def label_pull_requests(event, gh, *args, session, **kwargs):
    """
    Add labels to PRs based on which files were modified.
    """
    await handlers.add_labels(event, gh)


@router.register("pull_request", action="closed")
async def on_closed_pull_request(event, gh, *args, session, **kwargs):
    """
    Respond to the pull request closed
    """
    await handlers.close_pr_gitlab_branch(event, gh)

    await handlers.close_pr_mirror(event, gh)
