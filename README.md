This bot is based off of the following tutorials:

* https://docs.github.com/en/free-pro-team@latest/developers/apps/setting-up-your-development-environment-to-create-a-github-app
* https://docs.github.com/en/free-pro-team@latest/developers/apps/using-the-github-api-in-your-app

Follow the instructions in that documentation to get started.

## Install

To run the code, make sure you have [Bundler](http://gembundler.com/) installed; then enter `bundle install` on the command line.

## Set environment variables

1. Create a `.env` file.
2. Add your GitHub App's private key, app ID, and webhook secret to the `.env` file.

## Run the server

1. Run `ruby template_server.rb` or `ruby server.rb` on the command line.
1. View the default Sinatra app at `localhost:3000`.
