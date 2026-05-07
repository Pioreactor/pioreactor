#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
CRUDINI=/opt/pioreactor/venv/bin/crudini

if [ ! -x "$CRUDINI" ]; then
    echo "Missing executable $CRUDINI" >&2
    exit 1
fi

if [ -f "$CONFIG" ]; then
    LEADER_HOSTNAME=$("$CRUDINI" --get "$CONFIG" cluster.topology leader_hostname)
else
    LEADER_HOSTNAME=""
fi

if [ -n "$LEADER_HOSTNAME" ] && [ "$LEADER_HOSTNAME" = "$(hostname)" ]; then
    "$CRUDINI" --set "$CONFIG" bioreactor initial_cumulative_media_added_ml 0
    "$CRUDINI" --set "$CONFIG" bioreactor initial_cumulative_alt_media_added_ml 0
    "$CRUDINI" --set "$CONFIG" bioreactor initial_cumulative_waste_removed_ml 0
    chown pioreactor:www-data "$CONFIG"

    sudo -u pioreactor -i pios sync-configs || :
fi
