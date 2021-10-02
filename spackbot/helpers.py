# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)


from io import StringIO
import aiohttp
import contextlib
import gidgethub
import logging
import os
import re
import tempfile

from datetime import datetime

"""Shared function helpers that can be used across routes"
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spackbot")

spack_develop_url = "https://github.com/spack/spack"
spack_gitlab_url = "https://gitlab.spack.io"
spack_upstream = "git@github.com:spack/spack"

# Spack has project ID 2
gitlab_spack_project_url = "https://gitlab.spack.io/api/v4/projects/2"

package_path = r"^var/spack/repos/builtin/packages/(\w[\w-]*)/package.py$"

# Bot name can be modified in the environment
botname = os.environ.get("SPACKBOT_NAME", "@spackbot")
logging.info(f"bot name is {botname}")

# Aliases for spackbot so spackbot doesn't respond to himself
aliases = ["spack-bot", "spackbot", "spack-bot-develop", botname]
alias_regex = "(%s)" % "|".join(aliases)


async def list_packages():
    """
    Get a list of package names
    """
    # Don't provide endpoint with credentials!
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://spack.github.io/packages/data/packages.json"
        ) as response:
            response = await response.json()

    return [x.lower() for x in response]


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
    control(*cmd, _out=res, _err=err, _ok_code=ok_codes)
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
