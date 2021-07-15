# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging
import random
import requests
import re
import os

from .helpers import found, alias_regex, gitlab_spack_project_url, spack_gitlab_url
from gidgethub import routing


logger = logging.getLogger(__name__)
router = routing.Router()

# We can only make the request with a GITLAB TOKEN
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")


async def run_pipeline(event, gh):
    """
    Make a request to re-run a pipeline.
    """
    # Get the pull request number
    pr_url = event.data["issue"]["pull_request"]["url"]
    number = pr_url.split("/")[-1]

    # We need the pull request branch
    response = requests.get(pr_url)
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

    # We need the branch name plus number to assemble the GitLab CI
    branch = pr["head"]["ref"]
    branch = "github/pr%s_%s" % (number, branch)

    url = "%s/pipeline?ref=%s" % (gitlab_spack_project_url, branch)
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    response = requests.post(url, headers=headers)
    result = response.json()
    if "detailed_status" in result and "details_path" in result["detailed_status"]:
        url = "%s/%s" % (spack_gitlab_url, result["detailed_status"]["details_path"])
        return "I've started that [pipeline](%s) for you!" % url
    return "I had a problem triggering the pipeline."


@router.register("issue_comment", action="created")
async def add_comments(event, gh, *args, session, **kwargs):
    """
    Respond to request to re-run pipeline
    """
    # We can only tell PR and issue comments apart by this field
    if "pull_request" not in event.data["issue"]:
        return

    # spackbot should not respond to himself!
    if re.search(alias_regex, event.data["comment"]["user"]["login"]):
        return

    # Respond with appropriate messages
    comment = event.data["comment"]["body"]

    # @spackbot run pipeline | @spackbot re-run pipeline
    message = None
    if re.search("@spackbot (re-)?run pipeline", comment, re.IGNORECASE):
        logger.info(f"Responding to request to re-run pipeline...")
        if not GITLAB_TOKEN:
            message = "I'm not able to re-run the pipeline now because I don't have authentication."
        else:
            message = await run_pipeline(event, gh)
    if message:
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})
