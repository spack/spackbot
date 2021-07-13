# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging
import random
import re

from gidgethub import routing


logger = logging.getLogger(__name__)
router = routing.Router()

style_message = """
It looks like you had an issue with style checks! To fix this, you can run:

```bash
$ spack style --fix
```

And then update the pull request here. Or you can just say `@spackbot fix style` and I'll do it!
"""


@router.register("check_run", action="completed")
async def add_style_comments(event, gh, *args, session, **kwargs):
    """If a style check fails, add suggested fixes to user."""

    # Nothing to do with success
    if event.data["check_run"]["conclusion"] == "success":
        return

    # If it's not a style check, we don't care
    if event.data["check_run"]["name"] != "style":
        return

    # If we get here, we have a style failure
    # Find the pull request that is matched to the repository. It looks like
    # checks are shared across different repos (e.g., a fork and upstream)
    repository = event.data["repository"]["full_name"]
    for pr in event.data["check_run"]["pull_requests"]:
        if repository in pr["url"]:

            number = pr["url"].split("/")[-1]
            comments_url = "https://api.github.com/repos/%s/issues/%s/comments" % (
                repository,
                number,
            )
            await gh.post(comments_url, {}, data={"body": style_message})
            break
