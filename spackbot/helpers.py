# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)


from io import StringIO
import contextlib
import os
import tempfile
import re
import gidgethub

"""Shared function helpers that can be used across routes"
"""

spack_develop_url = "https://github.com/spack/spack"
spack_gitlab_url = "https://gitlab.spack.io"

# Spack has project ID 2
gitlab_spack_project_url = "https://gitlab.spack.io/api/v4/projects/2"

package_path = r"^var/spack/repos/builtin/packages/(\w[\w-]*)/package.py$"

# Aliases for spackbot so spackbot doesn't respond to himself
aliases = ["spack-bot", "spackbot", "spack-bot-develop"]
alias_regex = "(%s)" % "|".join(aliases)


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
