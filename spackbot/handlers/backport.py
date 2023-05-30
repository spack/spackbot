# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import re

from collections import defaultdict

# TODO GBB: make this threadsafe
backport_backlog = defaultdict(lambda: [])
backport_version_re = f"{helpers.botname} backport (v?\\d+.\\d+)"


async def _parse_backport_version(comment):
    target_match = re.match(backport_version_re, comment, re.IGNORE_CASE)

    if not target_match:
        error = f"Failed parsing backport version from {comment}."
        message = error + f" Backports must match {backport_version_re}."
        raise ValueError(error)

    target = target_match.group(1)
    if not target.startswith("v"):
        target = "v" + target

    return target


async def register_future_backport(event, gh, *args, **kwargs):
    global backport_backlog

    try:
        target = await _parse_backport_version(
            event.data["comment"]["body"]
        )
    except ValueError as e:
        return e.message

    pr_number = event.data["issue"]["number"]
    # TODO GBB: This probably isn't thread safe
    backport_backlog[pr_number] = backport_backlog[pr_number] + [target]

    return f"Registered {target} as a backport target for this PR {pr_number}".


async def backport_pr_from_comment(event, gh, *args, **kwargs):
    pr_number = event.data["issue"]["number"]
    try:
        target = await _parse_backport_version(
            event.data["comment"]["body"]
        )
    except ValueError as e:
        return e.message

    await backport_pr(pr_number, target)


async def backport_pr_from_merge(event, gh, *args, **kwargs):
    pr_number = event.data["pull_request"]["number"]
    targets = backport_backlog[pr_number]

    for target in targets:
        await backport_pr(pr_number, target)


async def backport_pr(pr_number, target):
    # TODO GBB: implement this
    # psuedocode
    # create branch pr_#_backport_spackbot identical to head branch of PR
    # rebase pr_#_backport_spackbot on target
    # if successful
    #     create pr from pr_#_backport_spackbot to target
    #     merge pr from previous step
    # else
    #     abort rebase
    #     create pr from pr_#_backport_spackbot to target
    #     comment on pr with the following
    #         tag author of base PR
    #         tag user who initiated backport (need to update data structure to track this
    #         request manual intervention
    pass

# TODO GBB: This goes in another file
async def manage_backports_pr():  # TODO GBB: what are the args here?
    # args
    #  user
    #  email
    #  fork_url
    #  remote_branch
    #  local_branch
    #  new_local_name
    #  target_branch
    with helpers.temp_dir() as cwd:
        git.clone(helpers.spack_upstream, "spack")
        os.chdir("spack")

        git.config("user.name", user)
        git.config("user.email", email)

        # Fetch the PR branch and fetch the target branch
        git.remote("add", "fork", fork_url)
        helpers.run_command(
            git, ["fetch", "fork", f"{remote_branch}:{local_branch}"]
        )
        helpers.run_comand(git, ["fetch", "origin", target_branch])

        # Checkout the PR branch, and create a new copy rebased on the target
        helpers.run_command(git, ["checkout", local_branch])
        helpers.run_command(git, ["checkout", "-b", new_local_name])

        try:
            helpers.run_command(git, ["rebase", target_branch])
        except Exception:
            # TODO GBB: what do I do here?
            pass

        try:
            helpers.run_command(git, ["push", "origin", new_local_name])
        except Exception:
            # TODO GBB: properly log and report failure here
            pass

        # TODO GBB: Create PR and merge it
