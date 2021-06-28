# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import contextlib
import logging
import os
import re
import tempfile

import gidgethub
from sh.contrib import git
from gidgethub import routing

logger = logging.getLogger(__name__)
router = routing.Router()

spack_develop_url = "https://github.com/spack/spack"

package_path = r"^var/spack/repos/builtin/packages/(\w[\w-]*)/package.py$"

non_reviewers_comment = """\
  @{non_reviewers} can you review this PR?

  This PR modifies the following package(s), for which you are listed as a maintainer:

  * {packages_with_maintainers}
"""

no_maintainers_comment = """\
Hi @{author}! I noticed that the following package(s) don't yet have maintainers:

* {packages_without_maintainers}

Are you interested in adopting any of these package(s)? If so, simply add the following to the package class:
```python
    maintainers = ['{author}']
```
If not, could you contact the developers of this package and see if they are interested? Please don't add maintainers without their consent.

_You don't have to be a Spack expert or package developer in order to be a "maintainer", it just gives us a list of users willing to review PRs or debug issues relating to this package. A package can have multiple maintainers; just add a list of GitHub handles of anyone who wants to volunteer._
"""


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
    """Create a temporary directory, cd into it, destroy it and cd back when done."""
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(pwd)


async def parse_maintainers_from_patch(gh, pull_request):
    """Get any new or removed maintainers from the patch data in the PR.

    We parse this from the patch because running the spack from the PR as this
    bot is unsafe; the bot is privileged and we do not trust code from PRs.

    """
    maintainers = {}
    async for file in gh.getiter(pull_request["url"] + "/files"):
        filename = file["filename"]
        if not filename.endswith("package.py"):
            continue

        pkg = re.search(r"/([^/]+)/package.py", filename).group(1)

        code = file["patch"]
        arrays = re.findall("maintainers\s*=\s*\[[^\]]*\]", code)
        for array in arrays:
            file_maintainers = re.findall("['\"][^'\"]*['\"]", array)
            for m in file_maintainers:
                maintainers.setdefault(pkg, set()).add(m.strip("'\""))

    return maintainers


async def find_maintainers(gh, packages, repository, pull_request, number):
    """Return an array of packages with maintainers, an array of packages
    without maintainers, and a set of maintainers.

    Ignore the author of the PR, as they don't need to review their own PR.
    """
    author = pull_request["user"]["login"]

    # lists of packages
    with_maintainers = []
    without_maintainers = []

    # parse any added/removed maintainers from the PR. Do NOT run the spack from the PR
    patch_maintainers = await parse_maintainers_from_patch(gh, pull_request)
    logger.info(f"Maintainers from patch: {patch_maintainers}")

    all_maintainers = set()
    with temp_dir() as cwd:
        # Clone spack develop (shallow clone for speed)
        # WARNING: We CANNOT run spack from the PR, as it is untrusted code.
        # WARNING: If we run that, an attacker could run anything as this bot.
        git("clone", "--depth", "1", spack_develop_url)

        # Add `spack` to PATH
        os.environ["PATH"] = f"{cwd}/spack/bin:" + os.environ["PATH"]
        from sh import spack

        for package in packages:
            logger.info(f"Package: {package}")

            # Query maintainers from develop
            maintainers = spack("maintainers", package, _ok_code=(0, 1)).split()
            maintainers = set(maintainers)

            # add in maintainers from the PR patch
            maintainers |= patch_maintainers.get(package, set())

            logger.info("Maintainers: %s" % ", ".join(sorted(maintainers)))

            if not maintainers:
                without_maintainers.append(package)
                continue

            # No need to ask the author to review their own PR
            if author in maintainers:
                maintainers.remove(author)

            if maintainers:
                with_maintainers.append(package)
                all_maintainers |= maintainers

    return with_maintainers, without_maintainers, all_maintainers


async def found(coroutine):
    """Wrapper for coroutines that returns None on 404, result otherwise."""
    try:
        return await coroutine
    except gidgethub.HTTPException as e:
        if e.status_code == 404:
            return None
        raise


async def add_reviewers(gh, repository, pull_request, number):
    """Add a comment on a PR to ping maintainers to review the PR.

    If a package does not have any maintainers yet, request them.
    """
    logger.info(f"Looking for reviewers for PR #{number}...")

    packages = await changed_packages(gh, pull_request)

    # Don't ask maintainers for review if hundreds of packages are modified,
    # it's probably just a license or Spack API change, not a package change.
    if len(packages) > 100:
        return

    maintained_pkgs, unmaintained_pkgs, maintainers = await find_maintainers(
        gh, packages, repository, pull_request, number
    )

    if maintainers:
        # See which maintainers have permission to be requested for review
        # Requires at least "read" permission.
        reviewers = []
        non_reviewers = []
        for user in maintainers:
            logger.info(f"User: {user}")

            collaborators_url = repository["collaborators_url"]
            if not await found(gh.getitem(collaborators_url, {"collaborator": user})):
                non_reviewers.append(user)
                continue

            result = await gh.getitem(
                collaborators_url + "/permission",
                {"collaborator": user},
            )
            level = result["permission"]
            logger.info(f"Permission level: {level}")
            reviewers.append(user)

        # If they have permission, add them
        # https://docs.github.com/en/rest/reference/pulls#request-reviewers-for-a-pull-request
        if reviewers:
            logger.info(f"Requesting review from: {reviewers}")

            # There is a limit of 15 reviewers, so take the first 15
            await gh.post(
                pull_request["url"] + "/requested_reviewers",
                {},
                data={"reviewers": reviewers[:15]},
            )

        # If not, give them permission and comment
        if non_reviewers:
            logger.info(f"Adding collaborators: {non_reviewers}")

            # We do not want to give users write permission here, as write
            # permission allows people to submit approving reviews for
            # auto-merge. Instead, we'd like to give them triage, which allows
            # them to be requested, label the PR, etc., but not determine
            # whether it should be merged.
            # https://docs.github.com/en/rest/reference/repos#add-a-repository-collaborator
            for user in non_reviewers:
                await gh.put(
                    repository["collaborators_url"],
                    {"collaborator": user},
                    # TODO: Looks like the collaborators API does not yet support
                    # 'triage' here, so we use 'read' instead.
                    data={"permission": "read"},
                )

            # https://docs.github.com/en/rest/reference/issues#create-an-issue-comment
            comment_body = non_reviewers_comment.format(
                packages_with_maintainers="\n* ".join(sorted(maintained_pkgs)),
                non_reviewers=" @".join(sorted(non_reviewers)),
            )
            await gh.post(pull_request["comments_url"], {}, data={"body": comment_body})

        # Ask people to maintain packages that don't have maintainers.
        if unmaintained_pkgs:
            # Ask for maintainers
            # https://docs.github.com/en/rest/reference/issues#create-an-issue-comment
            comment_body = no_maintainers_comment.format(
                author=pull_request["user"]["login"],
                packages_without_maintainers="\n* ".join(sorted(unmaintained_pkgs)),
            )
            await gh.post(pull_request["comments_url"], {}, data={"body": comment_body})


@router.register("pull_request", action="opened")
async def on_pull_request(event, gh, session):
    pull_request = event.data["pull_request"]
    repository = event.data["repository"]
    number = event.data["number"]

    await add_reviewers(gh, repository, pull_request, number)
