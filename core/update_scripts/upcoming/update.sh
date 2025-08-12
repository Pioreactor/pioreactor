#!/bin/bash

set -xeu


export LC_ALL=C

CONFIG=/home/pioreactor/.pioreactor/config.ini
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get "$CONFIG" cluster.topology leader_hostname)


sudo -u pioreactor mkdir /home/pioreactor/.pioreactor/models/

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    cp -u "$SCRIPT_DIR"/50-pioreactorui.conf /etc/lighttpd/conf-available/

    crudini --set "$CONFIG" od_reading.config duration_between_led_off_and_od_reading 0.125


fi
