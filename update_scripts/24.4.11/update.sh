#!/bin/bash

# this runs at startup on every boot.

set -x
set -e

export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    for file in $PIO_DIR/config_*.ini; do
        crudini --set "$file" pioreactor bioreactor pioreactor_20ml \
                --set "$file" pioreactor version 1.0
    done
     crudini --set $PIO_DIR/config.ini pioreactor

    sudo -u pioreactor pios sync-configs
fi
