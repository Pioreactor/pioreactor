#!/bin/bash

set -xeu

export LC_ALL=C

CONFIG=/home/pioreactor/.pioreactor/config.ini
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(/opt/pioreactor/venv/bin/crudini --get "$CONFIG" cluster.topology leader_hostname)

sudo systemctl restart pioreactor_startup_run@monitor.service || :

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service || :
fi
