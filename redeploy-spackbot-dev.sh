#!/bin/bash
set -e
set -x

project_root=$(pwd)

gh_user=kwryankrattiger
image_tag=0.0.1

# Rebuild images
docker build -f ${project_root}/Dockerfile -t ghcr.io/${gh_user}/spackbot:${image_tag} ${project_root}
docker build -f ${project_root}/workers/Dockerfile -t ghcr.io/${gh_user}/spackbot-workers:${image_tag} ${project_root}
docker push ghcr.io/${gh_user}/spackbot:${image_tag}
docker push ghcr.io/${gh_user}/spackbot-workers:${image_tag}

# Rollout with the new containers
kubectl -n spack rollout restart deployment spackbotdev-spack-io
kubectl -n spack rollout restart deployment spackbotdev-workers
kubectl -n spack rollout restart deployment spackbotdev-lworkers
