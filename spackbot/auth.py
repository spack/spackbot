# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import logging
import os
import re
import time

import aiohttp
import gidgethub.apps as gha
from aiohttp import web
from dotenv import load_dotenv
from gidgethub import aiohttp as gh_aiohttp

load_dotenv()

logger = logging.getLogger("spackbot")

#: Location for authenticatd app to get a token for one of its installations
INSTALLATION_TOKEN_URL = "app/installations/{installation_id}/access_tokens"

#: get app parameters we expect in environment or .env
PRIVATE_KEY = os.environ.get("GITHUB_PRIVATE_KEY")

APP_IDENTIFIER = os.environ.get("GITHUB_APP_IDENTIFIER")
REQUESTER = os.environ.get("GITHUB_APP_REQUESTER")

routes = web.RouteTableDef()


class TokenCache:
    """
    Cache for web tokens with an expiration.
    """

    def __init__(self):
        # token name to (expiration, token) tuple
        self._tokens = {}

    async def get_token(self, name, renew, *, time_needed=60):
        """Get a cached token, or renew as needed."""
        expires, token = self._tokens.get(name, (0, ""))

        now = time.time()
        if expires < now + time_needed:
            expires, token = await renew()
            self._tokens[name] = (expires, token)

        return token


#: Cache of web tokens for the app
_tokens = TokenCache()


def parse_isotime(timestr):
    """Convert UTC ISO 8601 time stamp to seconds in epoch"""
    if timestr[-1] != "Z":
        raise ValueError(f"Time String '{timestr}' not in UTC")
    return int(time.mktime(time.strptime(timestr[:-1], "%Y-%m-%dT%H:%M:%S")))


async def get_jwt():
    """Get a JWT from cache, creating a new one if necessary."""

    async def renew_jwt():
        # GitHub requires that you create a JWT signed with the application's
        # private key. You need the app id and the private key, and you can
        # use this gidgethub method to create the JWT.
        now = time.time()
        jwt = gha.get_jwt(app_id=APP_IDENTIFIER, private_key=PRIVATE_KEY)

        # gidgethub JWT's expire after 10 minutes (you cannot change it)
        return (now + 10 * 60), jwt

    return await _tokens.get_token("JWT", renew_jwt)


async def authenticate_installation(payload):
    """Get an installation access token for the application.

    Renew the JWT if necessary, then use it to get an installation access
    token from github, if necessary.

    """
    installation_id = payload["installation"]["id"]

    async def renew_installation_token():
        async with aiohttp.ClientSession() as session:
            gh = gh_aiohttp.GitHubAPI(session, REQUESTER)

            # Use the JWT to get a limited-life OAuth token for a particular
            # installation of the app. Note that we get a JWT only when
            # necessary -- when we need to renew the installation token.
            logger.debug("Installation ID: %s" % installation_id)
            result = await gh.post(
                INSTALLATION_TOKEN_URL,
                {"installation_id": installation_id},
                data=b"",
                accept="application/vnd.github.machine-man-preview+json",
                jwt=await get_jwt(),
            )

            expires = parse_isotime(result["expires_at"])
            token = result["token"]
            return (expires, token)

    return await _tokens.get_token(installation_id, renew_installation_token)


def fix_private_key():
    """Fix some discrepancies between Docker's --env-file support and python dotenv.

    Docker double-escapes \n's so they come through as \\n. It also preserves
    quotes from the .env file, while dotenv does not.

    """
    global PRIVATE_KEY

    # If we are given a file, load into variable
    if PRIVATE_KEY and os.path.exists(PRIVATE_KEY):
        with open(PRIVATE_KEY, "r") as handle:
            PRIVATE_KEY = handle.read()

    if PRIVATE_KEY:
        PRIVATE_KEY = re.sub(r"\\+", r"\\", PRIVATE_KEY)
        PRIVATE_KEY = re.sub(r"\\n", r"\n", PRIVATE_KEY)
        PRIVATE_KEY = PRIVATE_KEY.strip("'\"")


# Fix private key ONCE on app init
fix_private_key()
