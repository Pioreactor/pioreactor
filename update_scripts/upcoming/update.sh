#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    crudini  --set /home/pioreactor/.pioreactor/config.ini ui.overview.cards profiles 1
    crudini  --set /home/pioreactor/.pioreactor/config.ini storage experiment_profile_dir /home/pioreactor/.pioreactor/experiment_profiles

fi

# update firmware to 0.4
sudo cp "$SCRIPT_DIR"/main.elf /usr/local/bin/main.elf
sudo systemctl restart load_rp2040.service || :
echo "Added new main.elf firmware."
