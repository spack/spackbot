import aiohttp
import asyncio
import logging
import os
import tempfile
import zipfile

from datetime import datetime

from redis import Redis
from rq import Queue

from spackbot.helpers import gitlab_spack_project_url, pr_mirror_base_url

logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")
QUERY_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


async def find_latest_pipeline(url, headers, session):
    async with session.get(url, headers=headers) as response:
        pipeline_objects = await response.json()

    latest_p_obj = None

    if pipeline_objects:
        latest_p_obj = pipeline_objects[0]
        latest_time = datetime.strptime(latest_p_obj["updated_at"], QUERY_TIME_FORMAT)

        for i in range(1, len(pipeline_objects)):
            p_obj = pipeline_objects[i]
            updated = datetime.strptime(p_obj["updated_at"], QUERY_TIME_FORMAT)
            if updated > latest_time:
                latest_time = updated
                latest_p_obj = p_obj

    return latest_p_obj


async def retrieve_artifacts(url, headers, dl_folder, session):
    save_path = os.path.join(dl_folder, "artifacts.zip")

    async with session.get(url, headers=headers) as response:
        if not os.path.exists(dl_folder):
            os.makedirs(dl_folder)

        with open(save_path, "wb") as fd:
            async for chunk in response.content.iter_chunked(65536):
                fd.write(chunk)

    zip_file = zipfile.ZipFile(save_path)
    zip_file.extractall(dl_folder)
    zip_file.close()

    os.remove(save_path)


async def download_spack_lock_files(url, headers, download_dir, session):
    async with session.get(url, headers=headers) as response:
        job_objects = await response.json()

    folder_list = []

    if job_objects:
        for job in job_objects:
            artifacts_url = f"{gitlab_spack_project_url}/jobs/{job['id']}/artifacts"
            dl_folder = os.path.join(download_dir, job["name"])

            await retrieve_artifacts(artifacts_url, headers, dl_folder, session)

            for root, _, files in os.walk(dl_folder):
                if "spack.lock" in files:
                    folder_list.append(root)
                    break
            else:
                print(
                    f"Error: unable to find spack.lock in download folder {dl_folder}"
                )

    return folder_list


class WorkQueue:
    def __init__(self):
        logger.info(f"WorkQueue creating redis connection ({REDIS_HOST}, {REDIS_PORT})")
        self.redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
        logger.info(f"WorkQueue creating redis connection ({REDIS_HOST}, {REDIS_PORT})")
        self.copy_q = Queue(name="copy", connection=self.redis_conn)
        self.index_q = Queue(name="index", connection=self.redis_conn)

    def get_copy_queue(self):
        return self.copy_q

    def get_index_queue(self):
        return self.index_q


work_queue = WorkQueue()


async def run_in_subprocess(cmd_string):
    proc = await asyncio.create_subprocess_shell(
        cmd_string, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    print(f"[{cmd_string!r} exited with {proc.returncode}]")
    if stdout:
        print(f"[stdout]\n{stdout.decode()}")
    if stderr:
        print(f"[stderr]\n{stderr.decode()}")


async def copy_pr_binaries(pr_number, pr_branch, shared_pr_mirror_url):
    """Find the latest gitlab pipeline for the PR, get the spack.lock
    for each child pipeline, and for each one, activate the environment
    and issue the spack buildcache sync command to copy between the
    per-pr mirror and the shared pr mirror.
    """
    pipeline_ref = f"github/pr{pr_number}_{pr_branch}"
    pr_mirror_url = f"{pr_mirror_base_url}/{pipeline_ref}"
    pipelines_url = (
        f"{gitlab_spack_project_url}/pipelines?ref={pipeline_ref}&per_page=100"
    )
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

    # Create single new session for gitlab requests
    async with aiohttp.ClientSession() as session:
        latest_pipeline = await find_latest_pipeline(pipelines_url, headers, session)

        if not latest_pipeline:
            print(f"Unable to find latest pipeline for {pipeline_ref}")
            return

        print(f"found latest pipeline for {pipeline_ref}:")
        print(latest_pipeline)

        p_id = latest_pipeline["id"]

        jobs_url = f"{gitlab_spack_project_url}/pipelines/{p_id}/jobs"

        with tempfile.TemporaryDirectory() as tmp_dir_path:
            print(f"Downloading spack.lock files under: {tmp_dir_path}")
            folders = await download_spack_lock_files(
                jobs_url, headers, tmp_dir_path, session
            )

            for env_dir in folders:
                print(
                    f"Copying binaries from {pr_mirror_url} to {shared_pr_mirror_url}"
                )
                print(f"  using spack environment: {env_dir}")

                cmd_elements = [
                    "spack",
                    "-e",
                    env_dir,
                    "-d",
                    "buildcache",
                    "sync",
                    "--src-mirror-url",
                    pr_mirror_url,
                    "--dest-mirror-url",
                    shared_pr_mirror_url,
                ]

                await run_in_subprocess(" ".join(cmd_elements))

        # Clean up the per-pr mirror
        print(f"Deleting mirror: {pr_mirror_url}")

        cmd_elements = ["spack", "mirror", "destroy", "--mirror-url", pr_mirror_url]

        await run_in_subprocess(" ".join(cmd_elements))


async def update_mirror_index(mirror_url):
    """Use spack buildcache command to update index on remote mirror"""
    print(f"Updating binary index at {mirror_url}")

    cmd_elements = [
        "spack",
        "-d",
        "buildcache",
        "update-index",
        "--mirror-url",
        f"'{mirror_url}'",
    ]

    await run_in_subprocess(" ".join(cmd_elements))


async def test_job():
    print("Running a test spack command")

    cmd_elements = ["spack", "help", "--all"]

    await run_in_subprocess(" ".join(cmd_elements))
