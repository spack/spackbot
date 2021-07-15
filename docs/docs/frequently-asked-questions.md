# Frequently Asked Questions

## How do I make my own GitHub bot?

The basics of a bot come down to creating a service (a server somewhere) that 
has an app running to authenticate and respond to requests from GitHub. This means
that the app will be registered under your user account and installed for a repository,
and it's up to you to choose the language and deploy strategy that you like best.
We went with Python as spack is a Python library, however you could easily do Ruby or Go.
There are many good guides, and here we provide some resources that might be helpful:

 - [GitHub Docs Tutorial](https://docs.github.com/en/github-ae@latest/developers/apps/getting-started-with-apps/setting-up-your-development-environment-to-create-a-github-app) to get started with GitHub apps.
 - [Octomachinery](https://github.com/sanitizers/octomachinery): Python library to support creating a GitHub app
 - [Gitgethub](https://gidgethub.readthedocs.io/en/latest/apps.html): Another Python library for GitHub apps (used in Spackbot) and the [tutorial](https://github-bot-tutorial.readthedocs.io/en/latest/gidgethub-for-webhooks.html).
 - [bedevere](https://github.com/python/bedevere) and [miss-islington](https://github.com/python/miss-islington) example apps that uses Heroku.
 
 

## I have an idea for spackbot!

Great! Spackbot exists to help maintainers, reviewers, and contributors, and if you
have an idea for how to make spackbot better we want to hear from you! Please [get in contact with us](support).
