# Spackbot

This is a GitHub bot for the [Spack](https://github.com/spack/spack)
project. It automates various workflow tasks and handles jobs like:

* notifying maintainers about relevant pull requests
* adding them as reviewers if they are collaborators in the
  [Spack organization](https://github.com/spack)
* automatically labeling pull requests based on the files they modify

This list could easily expand in the future.

This app was built using [aiohttp](https://github.com/aio-libs/aiohttp)
and [gidgethub](https://github.com/brettcannon/gidgethub), based on
@Mariatta's excellent
[GitHub Bot Tutorial](https://github-bot-tutorial.readthedocs.io/en/latest/).

## How it works

Spackbot is a pretty typical GitHub bot. It runs in a container somewhere
in the cloud. A
[GitHub App](https://docs.github.com/en/developers/apps/about-apps) is
registered with the Spack project, and the app tells Spackbot about
events like pull requests being opened through
[webhook payloads](https://docs.github.com/en/developers/webhooks-and-events/webhook-events-and-payloads).
The Spackbot process in the container looks at these payloads and reacts
to them by calling commands through the
[GitHub API](https://docs.github.com/en/rest).

See Octomachinery's guide for
[responding to GitHub events](https://tutorial.octomachinery.dev/en/latest/octomachinery-for-github-apps.html)
for a detailed description of how this app is structured.

## Required environment variables

To deploy this, you'll need several environment variables set:

* `GITHUB_PRIVATE_KEY`: private key created by the GitHub App
* `GITHUB_APP_IDENTIFIER`: id of the App on GitHub
* `GITHUB_WEBHOOK_SECRET`: secret for webhooks, created when you created the GitHub App

In a development environment, you can put these in a `.env` file in the
directory where you run the app. In production, they should be set as
secrets in the deployment environment.

## Running the application

1. Get the root of this project in your `PYTHONPATH`
2. Run this:

   ```
   python3 -m spackbot
   ```

## License

Spack is distributed under the terms of both the MIT license and the
Apache License (Version 2.0). Users may choose either license, at their
option.

All new contributions must be made under both the MIT and Apache-2.0
licenses.

See [LICENSE-MIT](https://github.com/spack/spack-bot/blob/master/LICENSE-MIT),
[LICENSE-APACHE](https://github.com/spack/spack-bot/blob/master/LICENSE-APACHE),
[COPYRIGHT](https://github.com/spack/spack-bot/blob/master/COPYRIGHT), and
[NOTICE](https://github.com/spack/spack-bot/blob/master/NOTICE) for details.

SPDX-License-Identifier: (Apache-2.0 OR MIT)

LLNL-CODE-811652
