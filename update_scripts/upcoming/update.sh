#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    crudini  --set /home/pioreactor/.pioreactor/config.ini ui.overview.cards profiles 1

fi

# update firmware to 0.4
sudo cp "$SCRIPT_DIR"/main.elf /usr/local/bin/main.elf
sudo systemctl restart load_rp2040.service || :
echo "Added new main.elf firmware."
