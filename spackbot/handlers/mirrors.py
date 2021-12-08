# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging

from spackbot.helpers import pr_expected_base, pr_mirror_base_url
from spackbot.workers import copy_pr_binaries, update_mirror_index, work_queue

# If we don't provide a timeout, the default in RQ is 180 seconds
WORKER_JOB_TIMEOUT = 6 * 60 * 60

logger = logging.getLogger(__name__)


async def graduate_pr_binaries(event, gh):
    payload = event.data

    base_branch = payload["pull_request"]["base"]["ref"]
    is_merged = payload["pull_request"]["merged"]

    if is_merged and base_branch == pr_expected_base:
        pr_number = payload["number"]
        pr_branch = payload["pull_request"]["head"]["ref"]

        shared_mirror_url = f"{pr_mirror_base_url}/shared_pr_mirror"

        logger.info(
            f"PR {pr_number}/{pr_branch} merged to develop, graduating binaries"
        )

        copy_q = work_queue.get_copy_queue()
        copy_job = copy_q.enqueue(
            copy_pr_binaries,
            pr_number,
            pr_branch,
            shared_mirror_url,
            job_timeout=WORKER_JOB_TIMEOUT,
        )
        logger.info(f"Copy job queued: {copy_job.id}")

        # If the index job queue has a job queued already, there is no need to
        # schedule another one
        index_q = work_queue.get_index_queue()
        if len(index_q.get_job_ids()) <= 0:
            update_job = index_q.enqueue(
                update_mirror_index, shared_mirror_url, job_timeout=WORKER_JOB_TIMEOUT
            )
            logger.info(f"update-index job queued: {update_job.id}")
        else:
            logger.info("skipped queuing redundant update-index job")
