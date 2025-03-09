#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # new add_worker script
    ADD_WORKER_FILE="/usr/local/bin/add_new_pioreactor_worker_from_leader.sh"
    sudo cp "$SCRIPT_DIR"/add_new_pioreactor_worker_from_leader.sh $ADD_WORKER_FILE
    echo "Added new add_new_pioreactor_worker_from_leader.sh."

fi
