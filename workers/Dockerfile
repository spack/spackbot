FROM ghcr.io/spack/ubuntu-bionic:latest

COPY workers/requirements.txt /source/requirements.txt
COPY workers/entrypoint.sh /source/entrypoint.sh
COPY spackbot /source/spackbot

RUN pip3 install --upgrade pip setuptools wheel && \
    pip3 install -r /source/requirements.txt

WORKDIR /source
ENTRYPOINT ["/bin/bash", "/source/entrypoint.sh"]
