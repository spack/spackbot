# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)


import aiohttp
import contextlib
import gidgethub
import json
import logging
import os
import re
import tempfile

from datetime import datetime
from io import StringIO
from sh import ErrorReturnCode
from urllib.request import HTTPHandler, Request, build_opener
from urllib.parse import urlparse


"""Shared function helpers that can be used across routes"
"""

spack_builds_system_dir = "./spack/lib/spack/spack/build_systems"
spack_develop_url = "https://github.com/spack/spack"
spack_gitlab_url = "https://gitlab.spack.io"
spack_upstream = "git@github.com:spack/spack"

# Spack has project ID 2
gitlab_spack_project_url = os.environ.get(
    "GITLAB_SPACK_PROJECT_URL", "https://gitlab.spack.io/api/v4/projects/2"
)

package_path = r"^var/spack/repos/builtin/packages/(\w[\w-]*)/package.py$"

# Bot name can be modified in the environment
botname = os.environ.get("SPACKBOT_NAME", "@spackbot")

# Bucket where pr binary mirrors live
pr_mirror_base_url = os.environ.get(
    "PR_BINARIES_MIRROR_BASE_URL", "s3://spack-binaries-prs"
)
shared_pr_mirror_retire_after_days = os.environ.get(
    "SHARED_PR_MIRROR_RETIRE_AFTER_DAYS", 7
)
pr_shared_mirror = "shared_pr_mirror"
pr_expected_base = os.environ.get("PR_BINARIES_BASE_BRANCH", "develop")

publish_mirror_base_url = "s3://spack-binaries"

# Aliases for spackbot so spackbot doesn't respond to himself
aliases = ["spack-bot", "spackbot", "spack-bot-develop", botname]
alias_regex = "(%s)" % "|".join(aliases)

__spackbot_log_level = None
__supported_log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def get_logger(name):
    global __spackbot_log_level

    if not __spackbot_log_level:
        __spackbot_log_level = os.environ.get("SPACKBOT_LOG_LEVEL", "INFO").upper()

        if __spackbot_log_level not in __supported_log_levels:
            # Logging not yet configured, so just print this warning
            print(
                f"WARNING: Unknown log level {__spackbot_log_level}, using INFO instead."
            )
            __spackbot_log_level = "INFO"

        logging.basicConfig(level=__spackbot_log_level)

    return logging.getLogger(name)


logger = get_logger(__name__)
logger.info(f"bot name is {botname}")


async def list_packages():
    """
    Get a list of package names
    """
    # Don't provide endpoint with credentials!
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://packages.spack.io/data/packages.json"
        ) as response:
            response = await response.json()

    return [x["name"].lower() for x in response]


async def changed_packages(gh, pull_request):
    """Return an array of packages that were modified by a PR.

    Ignore deleted packages, since we can no longer query them for
    maintainers.

    """
    # see which files were modified
    packages = []
    async for f in gh.getiter(pull_request["url"] + "/files"):
        filename = f["filename"]
        status = f["status"]

        if status == "removed":
            continue

        match = re.match(package_path, filename)
        if not match:
            continue
        packages.append(match.group(1))

    return packages


@contextlib.contextmanager
def temp_dir():
    """
    Create a temporary directory, cd into it, destroy it and cd back when done.
    """
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(pwd)


async def get_user_email(gh, user):
    """
    Given a username, get the correct email based on creation date
    """
    response = await gh.getitem(f"https://api.github.com/users/{user}")
    created_at = datetime.strptime(response["created_at"].split("T", 1)[0], "%Y-%m-%d")
    split = datetime.strptime("2017-07-18", "%Y-%m-%d")
    if created_at > split:
        email = f"{response['id']}+{user}@users.noreply.github.com"
    else:
        email = f"{user}@users.noreply.github.com"
    return email


def run_command(control, cmd, ok_codes=None):
    """
    Run a spack or git command and get output and error
    """
    ok_codes = ok_codes or [0, 1]
    res = StringIO()
    err = StringIO()

    try:
        control(*cmd, _out=res, _err=err, _ok_code=ok_codes)
    except ErrorReturnCode as inst:
        logger.error(f"cmd {cmd} exited non-zero")
        logger.error(f"stdout from {cmd}:")
        logger.error(res.getvalue())
        logger.error(f"stderr from {cmd}:")
        logger.error(err.getvalue())
        raise inst

    return res.getvalue(), err.getvalue()


async def found(coroutine):
    """
    Wrapper for coroutines that returns None on 404, result or True otherwise.

    ``True`` is returned if the request was successful but the result would
    otherwise be ``False``-ish, e.g. if the request returns no content.
    """
    try:
        result = await coroutine
        return result or True
    except gidgethub.HTTPException as e:
        if e.status_code == 404:
            return None
        raise


async def post(url, headers):
    """
    Convenience method to create a new session and make a one-off
    post request, given a url and headers to include in the request.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as response:
            return await response.json()


async def get(url, headers):
    """
    Convenience method to create a new session and make a one-off
    get request, given a url and headers to include in the request.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return await response.json()


async def delete(url, headers):
    """
    Convenience method to create a new session and make a one-off
    delete request, given a url and headers to include in the request.
    """
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as response:
            return await response.json()


def synchronous_http_request(url, data=None, token=None):
    """
    Makes synchronous http request to the provided url, using the token for
    authentication.

    Args:

        url: the target of the http request
        data: optional dictionary containing request payload data.  After stringify
        and utf-8 encoding, this is passed directly to urllib.request.Request
        constructor.
        token: optional, the value to use as the bearer in the auth header

    Returns:

        http response or None if request could not be made

    TODO: The on_failure callback provided at job scheduling time is not
    TODO: getting called when it is defined as async. So this is a synchronous
    TODO: way using only standard lib calls to do what we do everywhere else by
    TODO: awaiting gh api methods.  Need to figure out if that is a bug, by design,
    TODO: or if I was just doing it wrong.
    """
    if not url:
        logger.error("No url provided")
        return None

    headers = {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if data:
        data = json.dumps(data).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers=headers,
    )

    opener = build_opener(HTTPHandler)
    response = opener.open(request)
    response_code = response.getcode()

    logger.debug(
        f"synchronous_http_request sent request to {url}, response code: {response_code}"
    )

    return response


def s3_parse_url(url, default_bucket="spack-binaries-prs", default_prefix="dummy"):
    parsed = {
        "bucket": default_bucket,
        "prefix": default_prefix,
    }

    if isinstance(url, str):
        url = urlparse(url)

    if url.scheme == "s3":
        parsed.update(
            {
                "bucket": url.netloc,
                "prefix": url.path.strip("/"),
            }
        )

    return parsed
