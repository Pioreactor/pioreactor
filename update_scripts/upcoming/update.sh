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

    # change config's ui.overview.cards to rename and add new entry
    crudini --set /home/pioreactor/.pioreactor/config.ini ui.overview.charts optical_density 1
    crudini --set /home/pioreactor/.pioreactor/config.ini ui.overview.charts raw_optical_density 0

    # remove unused config
    crudini --del /home/pioreactor/.pioreactor/config.ini dosing_automation.config max_volume_to_stop

fi

# fix any calibration / persistent cache permission issues
sudo chown pioreactor:www-data /home/pioreactor/.pioreactor/storage
sudo chmod g+srwx /home/pioreactor/.pioreactor/storage
