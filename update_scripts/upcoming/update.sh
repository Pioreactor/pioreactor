#!/bin/bash

set -xeu


export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    sudo rm /var/www/pioreactorui/contrib/jobs/03_temperature_control.yaml || :
    sudo rm /var/www/pioreactorui/contrib/jobs/04_dosing_control.yaml || :
    sudo rm /var/www/pioreactorui/contrib/jobs/06_led_control.yaml || :

    sudo rm /var/www/pioreactorui/contrib/charts/06_temperature.yaml || :
fi
