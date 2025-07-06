#!/bin/bash

set -xeu


export LC_ALL=C

LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    sudo -u pioreactor pios sync-configs || :

    # restart mqtt to db
    sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service || :
fi
