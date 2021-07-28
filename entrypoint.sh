#!/bin/bash

# If we have an ssh key bound, add it
if [[ -f "/root/.ssh/id_rsa" ]]; then
    printf "Found id_spackbot to authenticate write...\n"
    eval "$(ssh-agent -s)"
    ssh-add /root/.ssh/id_rsa
else
    printf "No id_spackbot found, will not have full permissions\n"
fi

ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
exec python3 -m spackbot
