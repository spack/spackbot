# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging

from gidgethub import routing
import spackbot.helpers as helpers
import spackbot.comments as comments

logger = logging.getLogger(__name__)
router = routing.Router()


async def count_packages(event, gh):
    """
    Count number of packages, and if >1, suggest multiple PRs.
    """
    pull_request = event.data["pull_request"]
    repository = event.data["repository"]["full_name"]
    number = event.data["number"]
    comments_url = "https://api.github.com/repos/%s/issues/%s/comments" % (
        repository,
        number,
    )

    logger.info(f" Counting packages for PR #{number}...")
    packages = await helpers.changed_packages(gh, pull_request)

    # Prepare response to suggest multiple pull requests

    # If the number of packages > 1, suggest multiple PRs.
    if len(packages) > 1:
        packages += "\n".join(["- %s" % pkg for pkg in packages])
        await gh.post(
            comments_url,
            {},
            data={"body": comments.multiple_packages.format(packages=packages)},
        )
