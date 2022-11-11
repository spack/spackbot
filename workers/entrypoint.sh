#!/bin/bash

# Define REDIS_HOST, REDIS_PORT and TASK_QUEUE_NAME in .env file or k8s
# deployment.  REDIS_HOST and REDIS_PORT define the hostname/ip and port
# of the redis instance, while TASK_QUEUE_NAME defines the name of the
# queue used for communication between the webservice and workers.
rq worker -u redis://${REDIS_HOST}:${REDIS_PORT} --with-scheduler ${WORKER_TASK_QUEUE}
