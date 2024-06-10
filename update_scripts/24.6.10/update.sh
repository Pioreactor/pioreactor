#!/bin/bash

set -xeu


export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # Define the path to the Mosquitto configuration file
    CONFIG_FILE="/etc/mosquitto/mosquitto.conf"

    # Use sed to remove lines containing 'log_type notice'
    sudo sed -i '/^log_type notice$/d' "$CONFIG_FILE"


fi
