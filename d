#!/bin/bash

CONTAINER_NAME=$1

if [ -z "$CONTAINER_NAME" ]; then
    echo "Pass container name: ./d [container_name]"
    echo -e "Running containers:\n$(docker ps --format '{{.Names}}')"
    exit 1
fi

exec docker exec -it "$CONTAINER_NAME" /bin/bash