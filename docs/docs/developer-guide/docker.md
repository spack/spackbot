# Developer Steps with Local Docker

This was an initial brief guide to development that might be useful if you
don't want to use docker compose.

## 1. Required environment variables

To deploy this, you'll need several environment variables set:

* `GITHUB_PRIVATE_KEY`: Private key created by the GitHub app.
* `GITHUB_APP_IDENTIFIER`: ID of the app on GitHub.
* `GITHUB_APP_REQUESTER`: Account the app appears as.
* `GITLAB_TOKEN`: GitLab API token
* `GITHUB_WEBHOOK_SECRET`: Secret for webhooks, set when you configured the
  GitHub app.

In a development environment, you can put these in a `.env` file in the
directory where you run the app. In production, they should be set as
secrets in the deployment environment (e.g., Kubernetes secrets).

## 2. Running the application

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

Next you would want to [install the app](install)
