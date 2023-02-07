# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import spackbot.comments as comments
import spackbot.helpers as helpers

from spackbot.workers import (
    fix_style_task,
    report_style_failure,
    get_queue,
    WORKER_JOB_TIMEOUT,
    TASK_QUEUE_SHORT,
)


logger = helpers.get_logger(__name__)


async def style_comment(event, gh):
    """
    Make a comment on how to fix style
    """
    # If we get here, we have a style failure
    # Find the pull request that is matched to the repository. It looks like
    # checks are shared across different repos (e.g., a fork and upstream)
    repository = event.data["repository"]["full_name"]  # "spack-test/spack"
    for pr in event.data["check_run"]["pull_requests"]:  # []
        if repository in pr["url"]:
            number = pr["url"].split("/")[-1]
            comments_url = (
                f"https://api.github.com/repos/{repository}/issues/{number}/comments"
            )
            await gh.post(comments_url, {}, data={"body": comments.style_message})


async def fix_style(event, gh, *args, **kwargs):
    """
    Respond to a request to fix style by placing a task in the work queue
    """
    job_metadata = {
        # This object is attached to job, so we can access it from within the
        # job's on_failure callback or from the job itself.
        "post_comments_url": event.data["issue"]["comments_url"],
        "token": kwargs["token"],
    }

    task_q = get_queue(TASK_QUEUE_SHORT)
    fix_style_job = task_q.enqueue(
        fix_style_task,
        event,
        job_timeout=WORKER_JOB_TIMEOUT,
        meta=job_metadata,
        on_failure=report_style_failure,
    )
    logger.info(f"Fix style job enqueued: {fix_style_job.id}")
