#!/bin/bash


# Options:
#  -v, --version          output the version number
#  -u, --url <url>        URL of the webhook proxy service. Default: https://smee.io/new
#  -t, --target <target>  Full URL (including protocol and path) of the target service the events will forwarded to. Default: http://127.0.0.1:PORT/PATH
#  -p, --port <n>         Local HTTP server port (default: 3000)
#  -P, --path <path>      URL path to post proxied requests to` (default: "/")
# -h, --help             output usage information

# SMEE_URL should come from .env file bound via docker-compose
printf "smee --url ${SMEE_URL} --target http://spackbot --port 8080\n"
smee --url ${SMEE_URL} --target http://spackbot --port 8080
