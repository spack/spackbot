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

## Interactions

The table below shows interactions that spackbot supports. For some, they are 
triggered by user interaction (an `@spackbot` command). Others are run automatically
with different events.

| Name | Description | Command |
|------|-------------|---------|
|labels| Add labels to newly open pull requests | |
|maintainers| Suggest reviewers (package maintainers) for newly opened pull request | |
|hello| Say hello to spackbot | `@spackbot hello`|
|help| Ask for help from spackbot | `@spackbot help` or `@spackbot commands`|
|style| Spackbot will detect a failed style check and tell you how to fix it | |
|fix style| The command to fix style will run `spack style --fix`| `@spackbot fix style`|

The interactions above are each represented by a Python file in [spackbot](spackbot).

## Developer Steps with Docker Compose

These steps will walk you through setting up a development server with docker-compose
and a "smee" service to emulate a URL.

### 1. Create a webhook receiver

Since we are developing and don't have a proper URL to use (a GitHub App setup
will not accept a localhost address) we need to go to [Smee](https://docs.github.com/en/developers/apps/getting-started-with-apps/setting-up-your-development-environment-to-create-a-github-app#step-1-start-a-new-smee-channel) channel to allow you to register a url that forwards
to localhost. Once you have a url that looks like this:

```bash
https://smee.io/VtrVSOmJV7haXpwH
```

You can proceed to step 2.

### 2. Create secrets

To create your secrets file, copy .env-dummy to .env (which is added to .gitignore)
and then add your smee URL there:

```bash
export SMEE_URL=https://smee.io/VtrVSOmJV7haXpwH
```

The other secrets we will populate after we register the app, discussed next.

### 3. Register a GitHub App

You should next register a [GitHub App](https://github.com/settings/apps) under your username.
You'll first need to create a  [Follow this link](https://github.com/settings/apps) and click "New GitHub App."

 - **GitHub App Name**: can be whatever you like, SpackBot Develop for example.
 - **Homepage URL**: you can put the repository here, https://github.com/spack/spack-bot
 - You don't need to identify or authorize users.
 - **Webhook URL** enter your smee url
 - **Repo Permissions** You want to add:
   - Administration: read and write
   - Discussions: read and write
   - Contents: read and write
   - Issues: read only
   - Pull Requests: read and write
   - checks: read only
   - deployments: read only
 - **Organization Permissions** none
   - Members: read and write
 - **User Permissions** none
 - **Subscribe to events**:
  - issue comment
  - pull requests
  - pull request review comment
  - status
  - check run
  - check suite
  - deployment status
 - It's safer to select to run only on your user account.
 
After you create the App you will be redirected to a screen that has the app ID and
secrets. Make a private key, and copy it to the [spackbot](spackbot) directory
for the app to see, named as `spack-bot-develop.private-key.pem`.

```bash
$ cp $DOWNLOADS/download-key.pem spack-bot-develop.private-key.pem
```

Make sure to add these variables to your .env, specifically adding:

 - GITHUB_PRIVATE_KEY the name of the file in the root here.
 - GITHUB_APP_IDENTIFIER is the "APP ID" at the top
 - GITHUB_APP_REQUESTER is your GitHub account
 - GITHUB_WEBHOOK_SECRET also needs to be added to your app.


### 4. Build and Start containers

You can then ask docker-compose to build:

```bash
$ docker-compose build
```

And start your containers!

```bash
$ docker-compose up -d
$ docker-compose restart
```

We do the restart to make sure the server and smee are running.
You should be able to see logs (and any errors) by way of:

```bash
$ docker-compose logs
smee_1      | smee --url https://smee.io/VtrVSOmJV7haXpwH --target http://spackbot --port 8080
smee_1      | Forwarding https://smee.io/VtrVSOmJV7haXpwH to http://spackbot
smee_1      | Connected https://smee.io/VtrVSOmJV7haXpwH
spackbot_1  | ======== Running on http://0.0.0.0:8080 ========
spackbot_1  | (Press CTRL+C to quit)
```
Now you can develop/make changes, and then restart the containers to restart the
server. Since [spackbot](spackbot) is bound to the app install location in the container,
your app will update with changes.


## Developer Steps with Local Docker

### 1. Required environment variables

To deploy this, you'll need several environment variables set:

* `GITHUB_PRIVATE_KEY`: Private key created by the GitHub app.
* `GITHUB_APP_IDENTIFIER`: ID of the app on GitHub.
* `GITHUB_APP_REQUESTER`: Account the app appears as.
* `GITHUB_WEBHOOK_SECRET`: Secret for webhooks, set when you configured the
  GitHub app.

In a development environment, you can put these in a `.env` file in the
directory where you run the app. In production, they should be set as
secrets in the deployment environment (e.g., Kubernetes secrets).

### 2. Running the application

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
$ docker run --rm -it --env-file .env -p 8080:8080 spack/spackbot
```

## Install the App

Whether you plan to run with docker-copmose or locally, you will need to install
the app to a repository to get the full functionality.
So the next step is to install your app, ideally to your fork of spack. To do this,
go back to the App in developer settings and click on it's public url, which
will look something like `https://github.com/apps/<appname>`. You can then click
to install the app to your fork of spack. Then make sure your app is running,
and open a pull request. If you watch the server logs you should see:

```console
$ docker-compose logs -f
spackbot_1  | INFO:aiohttp.access:172.19.0.2 [10/Jul/2021:18:11:17 +0000] "POST / HTTP/1.1" 200 174 "-" "GitHub-Hookshot/7621ac9"
smee_1      | POST http://spackbot:8080/ - 200
```

If there are any errors they will appear there.


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
