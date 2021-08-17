#!/bin/bash

# If the ssh directory doesn't exist, create it
if [[ ! -d "/root/.ssh" ]]; then
    printf "Creating non-existent directory ~/.ssh\n"
    mkdir -p /root/.ssh
fi

# If custom GITHUB_IDRSA is found in the environment, copy to where it should be
if [ ! -z ${GITHUB_IDRSA+x} ]; then 
   printf "Found custom idrsa, copying to correct location.\n"
   cp "${GITHUB_IDRSA}" /root/.ssh/
   cp "${GITHUB_IDRSA}.pub" /root/.ssh/

   # permissions should be 600 on private, 644 on public, 700 on .ssh directory
   chmod 600 /root/.ssh/id_rsa
fi

# List files for sanity check
printf "Files in ~/.ssh\n"
ls ~/.ssh

# If we have an ssh key bound, add it
if [[ -e "/root/.ssh/id_rsa" ]]; then
    printf "Found id_spackbot to authenticate write...\n"
    eval "$(ssh-agent -s)"
    ssh-add /root/.ssh/id_rsa
else
    printf "No id_spackbot found, will not have full permissions\n"
fi

ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
exec python3 -m spackbot
