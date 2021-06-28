# Spackbot

This is a GitHub bot for the [Spack](https://github.com/spack/spack)
project. It automates various workflow tasks and handles jobs like:

* Notifying maintainers about relevant pull requests;
* Adding maintainers as reviewers if they are in the
  [maintainers team](https://github.com/orgs/spack/teams/maintainers) in the
  [Spack organization](https://github.com/spack);
* Inviting new maintainers to the maintainers team; and
* Automatically labeling pull requests based on modified files.

This list could easily expand in the future.

This app was built using [aiohttp](https://github.com/aio-libs/aiohttp) and
[gidgethub](https://github.com/brettcannon/gidgethub), based on @Mariatta's
excellent
[GitHub Bot Tutorial](https://github-bot-tutorial.readthedocs.io/en/latest/).

## How it works

Spackbot is a pretty typical GitHub bot. It runs in a container somewhere in
the cloud. A
[GitHub App](https://docs.github.com/en/developers/apps/about-apps) is
registered with the Spack project, and the app tells Spackbot about events like
pull requests being opened through
[webhook payloads](https://docs.github.com/en/developers/webhooks-and-events/webhook-events-and-payloads).
The Spackbot process in the container looks at these payloads and reacts to
them by calling commands through the
[GitHub API](https://docs.github.com/en/rest).

## Required environment variables

To deploy this, you'll need several environment variables set:

* `GITHUB_PRIVATE_KEY`: Private key created by the GitHub app.
* `GITHUB_APP_IDENTIFIER`: ID of the app on GitHub.
* `GITHUB_APP_REQUESTER`: Account the app appears as.
* `GITHUB_WEBHOOK_SECRET`: Secret for webhooks, set when you configured the
  GitHub app.

In a development environment, you can put these in a `.env` file in the
directory where you run the app. In production, they should be set as
secrets in the deployment environment (e.g., Kubernetes secrets).

## Running the application

1. Get the root of this project in your `PYTHONPATH`
2. Run this:

   ```console
   $ python3 -m spackbot
   ```

You can also use the [container](https://hub.docker.com/r/spack/spackbot) to
run the application. It is built from the top-level `Dockerfile` and runs on
port 8080. You'll need to expose that port to run. You can pass an environment
file to docker as well. Here's an example:

```console
$ docker run --rm -it --env-file .env -p8080:8080 spack/spackbot
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
