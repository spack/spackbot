#!/bin/bash

# Define REDIS_HOST and REDIS_PORT in .env file or k8s deployment.  The queue
# from which workers take jobs is given the name "tasks" here.
rq worker -u redis://${REDIS_HOST}:${REDIS_PORT} --with-scheduler tasks
