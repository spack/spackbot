# Spackbot

![docs/assets/img/spackbot.png](docs/assets/img/spackbot.png)

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

Want to learn more? Read the

⭐️ [Spackbot Documentation](https://spack.github.io/spackbot) ⭐️

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
