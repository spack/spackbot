#!/bin/bash

# Make sure spack can be found by worker jobs
. $SPACK_ROOT/share/spack/setup-env.sh

# Define REDIS_HOST and REDIS_PORT in .env file or k8s deployment.  Workers
# always take jobs from the "copy" queue first and then the "index" queue
# when passed in this order.
rq worker -u redis://${REDIS_HOST}:${REDIS_PORT} --with-scheduler copy index
