# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import spackbot.helpers as helpers
from spackbot.helpers import (
    pr_mirror_base_url,
)
from spackbot.workers import (
    delete_pr_mirror,
    get_queue,
    TASK_QUEUE_LONG,
)

# If we don't provide a timeout, the default in RQ is 180 seconds
WORKER_JOB_TIMEOUT = 6 * 60 * 60

logger = helpers.get_logger(__name__)


async def close_pr_mirror(event, gh):
    payload = event.data

    # This should only be called when a PR is closed
    if not payload["pull_request"]["state"] == "closed":
        return

    # Get PR event info
    pr_number = payload["number"]
    pr_branch = payload["pull_request"]["head"]["ref"]

    pr_mirror_url = f"{pr_mirror_base_url}/pr{pr_number}_{pr_branch}"

    # Get task queue info
    ltask_q = get_queue(TASK_QUEUE_LONG)
    job_metadata = {
        "type": None,
        "pr_number": pr_number,
        "pr_branch": pr_branch,
    }

    # Delete the mirror
    job_metadata.update({"type": "delete"})
    del_job = ltask_q.enqueue(
        delete_pr_mirror,
        pr_mirror_url,
        meta=job_metadata,
        job_timeout=WORKER_JOB_TIMEOUT,
    )
    logger.info(f"Delete job queued: {del_job.id}")
