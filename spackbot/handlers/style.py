# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import spackbot.comments as comments


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
            comments_url = "https://api.github.com/repos/%s/issues/%s/comments" % (
                repository,
                number,
            )
            await gh.post(comments_url, {}, data={"body": comments.style_message})
