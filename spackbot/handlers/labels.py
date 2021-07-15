# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spackbot")


#: ``label_patterns`` maps labels to patterns that tell us to apply the labels.
#:
#: Entries in the ``dict`` are of the form:
#:
#: ```python
#: {
#:     "label": {
#:         "attr1": [r"regex1.1", r"regex1.2"],
#:         "attr2": [r"regex2.1", r"regex2.2", r"regex2.3"],
#:         "attr3": r"regex3.1",
#:         ...
#:     },
#:     ...
#: }
#: ```
#:
#: ``attr1``, ``attr2``, etc. are attributes on files in the PR (e.g., ``status``,
#: ``filename``, etc).  If all attrs for a label have at least one regex match,
#: then that label will be added to the PR.
label_patterns = {
    #
    # Package types
    #
    "intel": {"package": r"intel"},
    "python": {"package": [r"^python$", r"^py-"]},
    "R": {"package": [r"^r$", r"^r-"]},
    #
    # Package status
    #
    "new-package": {
        "filename": r"^var/spack/repos/builtin/packages/[^/]+/package.py$",
        "status": r"^added$",
    },
    "update-package": {
        "filename": r"^var/spack/repos/builtin/packages/[^/]+/package.py$",
        "status": [r"^modified$", r"^renamed$"],
    },
    #
    # Variables
    #
    "maintainers": {"patch": r"[+-] +maintainers +="},
    #
    # Directives
    #
    "new-version": {"patch": r"\+ +version\("},
    "conflicts": {"patch": r"\+ +conflicts\("},
    "dependencies": {"patch": r"\+ +depends_on\("},
    "extends": {"patch": r"\+ +extends\("},
    "virtual-dependencies": {"patch": r"\+ +provides\("},
    "patch": {"patch": r"\+ +patch\("},
    "new-variant": {"patch": r"\+ +variant\("},
    "resources": {"patch": r"\+ +resource\("},
    #
    # Functions
    #
    "external-packages": {"patch": r"[+-] +def determine_spec_details\("},
    "libraries": {"patch": r"[+-] +def libs\("},
    "headers": {"patch": r"[+-] +def headers\("},
    "smoke-tests": {"patch": r"[+-] +def test\("},
    #
    # Core spack
    #
    "architecture": {
        "filename": r"^lib/spack/spack/(architecture|operating_systems|platforms)"
    },
    "binary-packages": {"filename": r"^lib/spack/spack/binary_distribution"},
    "build-environment": {"filename": r"^lib/spack/spack/build_environment"},
    "build-systems": {"filename": r"^lib/spack/spack/build_systems"},
    "new-command": {
        "filename": r"^lib/spack/spack/cmd/[^/]+.py$",
        "status": r"^added$",
    },
    "commands": {
        "filename": r"^lib/spack/spack/cmd/[^/]+.py$",
        "status": r"^modified$",
    },
    "compilers": {"filename": r"^lib/spack/spack/compiler"},
    "directives": {"filename": r"^lib/spack/spack/directives"},
    "environments": {"filename": r"^lib/spack/spack/environment"},
    "fetching": {"filename": r"^lib/spack/spack/(fetch|url|util/url|util/web)"},
    "locking": {"filename": r"^lib/spack/(spack|llnl)/util/lock"},
    "modules": {"filename": r"^lib/spack/spack/modules"},
    "stage": {"filename": r"^lib/spack/spack/stage"},
    "tests": {"filename": r"^lib/spack/spack/test"},
    "utilities": {"filename": [r"^lib/spack/spack/util", r"^lib/spack/llnl"]},
    "versions": {"filename": r"^lib/spack/spack/version"},
    #
    # Documentation
    #
    "documentation": {"filename": r"^lib/spack/docs"},
    #
    # GitHub
    #
    "travis": {"filename": r"^\.travis"},
    "actions": {"filename": r"^\.github/actions"},
    "workflow": {"filename": r"^\.github/workflows"},
    "git": {"filename": r"^\.gitignore"},
    "flake8": {"filename": r"^\.flake8"},
    "licenses": {"filename": r"^LICENSE"},
    "gitlab": {"filename": r"^share/spack/gitlab"},
    #
    # Other
    #
    "defaults": {"filename": r"^etc/spack/defaults"},
    "vendored-dependencies": {"filename": r"^lib/spack/external"},
    "sbang": {"filename": r"sbang"},
    "docker": {"filename": [r"[Dd]ockerfile$", r"^share/spack/docker"]},
    "shell-support": {"filename": r"^share/spack/.*\.(sh|csh|fish)$"},
}


# compile all the regexes above, and ensure that all pattern dict values are lists
for label, pattern_dict in label_patterns.items():
    for attr in pattern_dict.keys():
        patterns = pattern_dict[attr]
        if not isinstance(patterns, list):
            patterns = [patterns]
        pattern_dict[attr] = [re.compile(s) for s in patterns]


async def add_labels(event, gh):
    """
    Add labels to a pull request
    """
    pull_request = event.data["pull_request"]
    number = event.data["number"]
    logger.info(f"Labeling PR #{number}...")

    # Iterate over modified files and create a list of labels
    # https://developer.github.com/v3/pulls/#list-pull-requests-files
    labels = []
    async for file in gh.getiter(pull_request["url"] + "/files"):
        filename = file["filename"]
        status = file["status"]
        logger.info(f"Filename: {filename}")
        logger.info(f"Status: {status}")

        # Add our own "package" attribute to the file, if it's a package
        match = re.match(
            r"var/spack/repos/builtin/packages/([^/]+)/package.py$", filename
        )
        file["package"] = match.group(1) if match else ""

        # If the file's attributes match any patterns in label_patterns, add
        # the corresponding labels.
        for label, pattern_dict in label_patterns.items():
            attr_matches = []
            # Pattern matches for for each attribute are or'd together
            for attr, patterns in pattern_dict.items():
                attr_matches.append(any(p.search(file[attr]) for p in patterns))
            # If all attributes have at least one pattern match, we add the label
            if all(attr_matches):
                labels.append(label)

    logger.info(f"Adding the following labels: {labels}")

    # https://developer.github.com/v3/issues/labels/#add-labels-to-an-issue
    if labels:
        await gh.post(pull_request["issue_url"] + "/labels", data=labels)
