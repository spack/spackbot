# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import spackbot.helpers as helpers
from spackbot.helpers import (
    pr_expected_base,
    pr_mirror_base_url,
    pr_shared_mirror,
    publish_mirror_base_url,
)
from spackbot.workers import (
    copy_pr_mirror,
    prune_mirror_duplicates,
    update_mirror_index,
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
    base_branch = payload["pull_request"]["base"]["ref"]
    is_merged = payload["pull_request"]["merged"]
    pr_number = payload["number"]
    pr_branch = payload["pull_request"]["head"]["ref"]
    event_project = event.data["repository"]["name"]

    pr_mirror_url = f"{pr_mirror_base_url}/{event_project}/pr{pr_number}_{pr_branch}"
    shared_pr_mirror_url = f"{pr_mirror_base_url}/{pr_shared_mirror}"

    # Get task queue info
    ltask_q = get_queue(TASK_QUEUE_LONG)
    copy_job = None
    job_metadata = {
        "type": None,
        "pr_number": pr_number,
        "pr_branch": pr_branch,
    }

    # PR Graduation Mirror is disabled
    if False and is_merged and base_branch == pr_expected_base:
        logger.info(
            f"PR {pr_number}/{pr_branch} merged to develop, graduating binaries"
        )

        # Copy all of the stack binaries from the PR to the shared PR
        # mirror.
        job_metadata.update({"type": "copy"})
        copy_job = ltask_q.enqueue(
            copy_pr_mirror,
            pr_mirror_url,
            shared_pr_mirror_url,
            meta=job_metadata,
            job_timeout=WORKER_JOB_TIMEOUT,
        )
        logger.info(f"Copy job queued: {copy_job.id}")

        # Prune duplicates that have been published after copy
        # since copy may have introduced duplicates for some reason
        job_metadata.update({"type": "prune"})
        shared_stack_pr_mirror_url = f"{shared_pr_mirror_url}/{{stack}}"
        publish_stack_mirror_url = (
            f"{publish_mirror_base_url}/{{stack}}/{pr_expected_base}"
        )
        prune_job = ltask_q.enqueue(
            prune_mirror_duplicates,
            shared_stack_pr_mirror_url,
            publish_stack_mirror_url,
            job_timeout=WORKER_JOB_TIMEOUT,
            depends_on=copy_job,
            meta=job_metadata,
        )
        logger.info(f"Pruning job queued: {prune_job.id}")

        # Queue a reindex for the stack mirror to attempt to run after
        # prune.
        job_metadata.update({"type": "reindex"})
        update_job = ltask_q.enqueue(
            update_mirror_index,
            shared_stack_pr_mirror_url,
            job_timeout=WORKER_JOB_TIMEOUT,
            depends_on=prune_job,
            meta=job_metadata,
        )
        logger.info(f"Reindex job queued: {update_job.id}")

    # Delete the mirror
    job_metadata.update({"type": "delete"})
    del_job = ltask_q.enqueue(
        delete_pr_mirror,
        pr_mirror_url,
        meta=job_metadata,
        job_timeout=WORKER_JOB_TIMEOUT,
        depends_on=copy_job,
    )
    logger.info(f"Delete job queued: {del_job.id}")
