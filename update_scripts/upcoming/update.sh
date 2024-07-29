#!/bin/bash

set -xeu


export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor

# all pioreactors get a unit_config, include leader-only pioworekrs
touch PIO_DIR/unit_config.ini


HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then


fi
