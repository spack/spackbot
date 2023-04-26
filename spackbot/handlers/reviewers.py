# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import collections
import os
import re

import sh
from sh.contrib import git
import spackbot.helpers as helpers
import spackbot.comments as comments
from gidgethub import BadRequest

logger = helpers.get_logger(__name__)


async def parse_maintainers_info_from_patch(gh, pull_request):
    """
    Get any new or removed maintainers from the patch data in the PR and
    parent class(es).

    We parse this from the patch because running the spack from the PR as this
    bot is unsafe; the bot is privileged and we do not trust code from PRs.

    """
    parents = {}
    maintainers = {}
    async for file in gh.getiter(pull_request["url"] + "/files"):
        filename = file["filename"]
        if not filename.endswith("package.py"):
            continue

        pkg = re.search(r"/([^/]+)/package.py", filename).group(1)

        code = file["patch"]
        arrays = re.findall(r"maintainers(?:\(|\s*=\s*\[)[^\]\)]*(?:\)|\])", code)
        for array in arrays:
            file_maintainers = re.findall("['\"][^'\"]*['\"]", array)
            for m in file_maintainers:
                maintainers.setdefault(pkg, set()).add(m.strip("'\""))

        arrays = re.findall(r"class ([^\(]+)\(([^\(]+)\)", code)
        for array in arrays:
            parents[array[0]] = array[1].split(",")

    return maintainers, parents


async def find_maintainers(gh, packages, repository, pull_request, number):
    """
    Return an array of packages with maintainers, an array of packages
    without maintainers, and a set of maintainers.

    Ignore the author of the PR, as they don't need to review their own PR.
    """
    author = pull_request["user"]["login"]

    # lists of packages
    with_maintainers = []
    without_maintainers = []

    # parse any added/removed maintainers from the PR. Do NOT run spack from the PR
    patch_maintainers, parents = await parse_maintainers_info_from_patch(
        gh, pull_request
    )
    logger.info(f"Maintainers from patch: {patch_maintainers}")
    logger.info(f"Classes from patch: {parents}")

    all_maintainers = set()
    with helpers.temp_dir() as cwd:
        # Clone spack develop (shallow clone for speed)
        # WARNING: We CANNOT run spack from the PR, as it is untrusted code.
        # WARNING: If we run that, an attacker could run anything as this bot.
        git("clone", "--depth", "1", helpers.spack_develop_url)

        # Get spack executable
        spack = sh.Command(f"{cwd}/spack/bin/spack")

        # grab build system maintainers in case this is a new package
        core_maintainers = parse_build_system_maintainers()

        for package in packages:
            logger.info(f"Package: {package}")

            # Query maintainers from develop
            maintainers = spack("maintainers", package, _ok_code=(0, 1)).split()
            maintainers = set(maintainers)

            # add in maintainers from the PR patch
            maintainers |= patch_maintainers.get(package, set())

            # Add any maintainers from parent package(s) in case the package
            # is just being added and develop doesn't know anything about it.
            for p in parents[package]:
                maintainers |= core_maintainers.get(package, set())

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


async def add_issue_maintainers(event, gh, package_list):
    """
    Assign maintainers of packages based on issue title.

    **Important** this handler is currently not in use, but the logic
    is kept here to preserve for the future. We can edit the issue template
    to explicitly name a list of one or more packages, and then use that
    instead of parsing the title, as we do here.
    """
    # Add extra space to start and end of title so we catch matches at ends
    title = " " + event.data["issue"]["title"].lower() + " "

    # Replace special characters with spaces
    title = re.sub(r"[!#%^*(){}:_&$+@\/\[\]]+", " ", title)

    # Does the title have a known package (must have space before and after)
    package_regex = "( %s )" % " | ".join(package_list)
    packages = re.findall(package_regex, title)

    # If we match a package in the title, look for maintainers to ping
    if packages:
        # Remove extra spacing that helped search
        packages = [x.strip() for x in packages]

        # Look for maintainers of the package
        messages = []
        with helpers.temp_dir() as cwd:
            git("clone", "--depth", "1", helpers.spack_develop_url)

            # Add `spack` to PATH
            os.environ["PATH"] = f"{cwd}/spack/bin:" + os.environ["PATH"]
            from sh import spack

            for package in packages:
                # Query maintainers from develop
                found_maintainers = spack(
                    "maintainers", package, _ok_code=(0, 1)
                ).split()
                if found_maintainers:
                    found_maintainers = " ".join(
                        ["@%s," % m for m in found_maintainers]
                    )
                    messages.append(
                        "- Hey %s, it looks like you might know about the %s package. Can you help with this issue?"
                        % (found_maintainers, package)
                    )

        # If we have maintainers, ping them for help in the issue
        if messages:
            comment = comments.maintainer_request.format(
                maintainers="\n".join(messages)
            )
            await gh.post(
                event.data["issue"]["comments_url"], {}, data={"body": comment}
            )


async def add_reviewers(event, gh):
    """
    Add a comment on a PR to ping maintainers to review the PR.

    If a package does not have any maintainers yet, request them.
    """
    # If it's sent from a comment, the PR needs to be retrieved
    if "pull_request" in event.data:
        pull_request = event.data["pull_request"]
        number = event.data["number"]
    else:
        pr_url = event.data["issue"]["pull_request"]["url"]
        pull_request = await gh.getitem(pr_url)
        number = pull_request["number"]

    repository = event.data["repository"]

    logger.info(f"Looking for reviewers for PR #{number}...")

    packages = await helpers.changed_packages(gh, pull_request)

    # Don't ask maintainers for review if hundreds of packages are modified,
    # it's probably just a license or Spack API change, not a package change.
    if len(packages) > 100:
        return

    maintained_pkgs, unmaintained_pkgs, maintainers = await find_maintainers(
        gh, packages, repository, pull_request, number
    )

    # Ask people to maintain packages that don't have maintainers.
    if unmaintained_pkgs:
        # Ask for maintainers
        # https://docs.github.com/en/rest/reference/issues#create-an-issue-comment
        unmaintained_pkgs = sorted(unmaintained_pkgs)
        comment_body = comments.no_maintainers_comment.format(
            author=pull_request["user"]["login"],
            packages_without_maintainers="\n* ".join(unmaintained_pkgs),
            first_package_without_maintainer=unmaintained_pkgs[0],
        )
        await gh.post(pull_request["comments_url"], {}, data={"body": comment_body})

    # for packages that *do* have maintainers listed
    if maintainers:
        # See which maintainers have permission to be requested for review
        # Requires at least "read" permission.
        reviewers = []
        non_reviewers = []
        for user in maintainers:
            logger.info(f"User: {user}")

            # https://api.github.com/repos/spack/spack/collaborators/{user}
            # will return 404 if the user is not a collaborator, BUT
            # https://api.github.com/repos/spack/spack/collaborators/{user}/permission
            # will show read for pretty much anyone for public repos. So we have to
            # check the first URL first.
            collaborators_url = repository["collaborators_url"]
            if not await helpers.found(
                gh.getitem(collaborators_url, {"collaborator": user})
            ):
                logger.info(f"Not found: {user}")
                non_reviewers.append(user)
                continue

            # only check permission once we know they're a collaborator
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

        # If not, try to make them collaborators and comment
        if non_reviewers:
            # If the repository has a team called "maintainers", we'll try to
            # add the non-reviewers to it. That team determines what
            # permissions the maintainers get on the repo.
            teams_url = repository["teams_url"]
            members_url = None
            async for team in gh.getiter(teams_url):
                if team["name"] == "maintainers":
                    # This URL will auto-invite the user if possible. It's not
                    # the same as the members_url in the teams_url response,
                    # and it seems like we have to construct it manually.
                    members_url = team["html_url"].replace(
                        "/github.com/", "/api.github.com/"
                    )
                    members_url += "/memberships{/member}"
                    logger.info(f"made members_url: {members_url}")
                    break

            if not members_url:
                logger.info("No 'maintainers' team; not adding collaborators")
            else:
                logger.info(f"Adding collaborators: {non_reviewers}")
                for user in non_reviewers:
                    try:
                        await gh.put(
                            members_url, {"member": user}, data={"role": "member"}
                        )
                    except BadRequest as e:
                        if e.status_code == 404:
                            logger.warning(
                                f"Skipping adding member {user}, likely already added: {e}"
                            )
                        else:
                            raise e

            # https://docs.github.com/en/rest/reference/issues#create-an-issue-comment
            comment_body = comments.non_reviewers_comment.format(
                packages_with_maintainers="\n* ".join(sorted(maintained_pkgs)),
                non_reviewers=" @".join(sorted(non_reviewers)),
            )
            await gh.post(pull_request["comments_url"], {}, data={"body": comment_body})


def parse_build_system_maintainers():
    classes = {}
    maintainers = collections.defaultdict(set)

    files = os.listdir(helpers.spack_build_systems_dir)
    for filename in files:
        if not filename.endswith(".py") and filename != "__init__.py":
            continue

        # Grab maintainers for the class(es) in the build system.
        #
        # Simplifying assumption: each class inherits from only one parent.
        with open(os.path.join(helpers.spack_build_systems_dir, filename)) as f:
            for ln in f:
                match = re.search(r"^class ([^\(]+)\(([^\)]*)", ln)
                if match:
                    cls = match.group(1)
                    parent = match.group(2)
                    classes[cls] = parent
                    inherited = maintainers.get(parent, set())
                    if inherited:
                        maintainers[cls] = inherited
                else:
                    match = re.search(r"maintainers\(([^\)]*)\)", ln)
                    if match:
                        users = [
                            m.strip()
                            for m in match.group(1).replace('"', "").split(",")
                        ]
                        maintainers[cls] = set(users)

    return maintainers
