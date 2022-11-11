FROM python:3.7

COPY workers/requirements.txt /source/requirements.txt

RUN pip3 install --upgrade pip setuptools wheel && \
    pip3 install -r /source/requirements.txt

COPY workers/install_aws.sh /source/install_aws.sh

RUN . /source/install_aws.sh

# make the worker trust GitHub's host key (and verify it)
# If GitHub's fingerprint changes, update the code below with a new one:
# https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# and rebuild this container.
RUN ssh-keyscan -t rsa github.com 2>/dev/null > github.key \
  && fingerprint=$(ssh-keygen -lf ./github.key | grep -o 'SHA256:[^ ]*') \
  && if [ "$fingerprint" != "SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8" ]; \
     then echo "GitHub key is invalid!" && exit 1; \
     fi \
  && mkdir -p /root/.ssh \
  && cat ./github.key >> /root/.ssh/known_hosts

# use identity file in /git_rsa (the mount point for our public/private keys)
RUN \
     echo "Host github.com"              >> /root/.ssh/config \
  && echo "IdentityFile /git_rsa/id_rsa" >> /root/.ssh/config

# ensure /root/.ssh has correct permissions
RUN chmod -R go-rwx /root/.ssh
RUN mkdir -p /git_rsa && chmod -R go-rwx /git_rsa

# copy app in last so that everything above can be cached
COPY workers/entrypoint.sh /source/entrypoint.sh
COPY spackbot /source/spackbot

WORKDIR /source
ENTRYPOINT ["/bin/bash", "/source/entrypoint.sh"]
