#!/bin/bash

set -xeu


export LC_ALL=C

LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if non-leader
if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    sudo reboot
fi
