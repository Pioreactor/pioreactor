#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    crudini --set /home/pioreactor/.pioreactor/config.ini ui.overview.cards profiles 1
    crudini --set /home/pioreactor/.pioreactor/config.ini od_reading.config smoothing_penalizer 6.0
    crudini --set /home/pioreactor/.pioreactor/config.ini growth_rate_calculating.config ekf_outlier_std_threshold 5.0
    sudo -u pioreactor pios sync-configs --shared || :

    # new add_worker script
    ADD_WORKER_FILE="/usr/local/bin/add_new_pioreactor_worker_from_leader.sh"
    sudo cp "$SCRIPT_DIR"/add_new_pioreactor_worker_from_leader.sh $ADD_WORKER_FILE
    echo "Added new add_new_pioreactor_worker_from_leader.sh."

fi

# update firmware to 0.5
MAIN_ELF="/usr/local/bin/main.elf"
sudo cp "$SCRIPT_DIR"/main.elf $MAIN_ELF
sudo systemctl restart load_rp2040.service || :
echo "Added new main.elf firmware."


# new huey
HUEY_SERVICE_FILE="/etc/systemd/system/huey.service"
sudo cp "$SCRIPT_DIR"/huey.service $HUEY_SERVICE_FILE
echo "Added new huey.service."


# cal fix from previous update
sudo -u pioreactor python "$SCRIPT_DIR"/cal_fix.py || :
