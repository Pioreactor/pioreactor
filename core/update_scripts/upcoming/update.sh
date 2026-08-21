#!/bin/bash

set -xeu

export LC_ALL=C

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

if ! sudo -u pioreactor -i pio config get camera use_ir_led --shared >/dev/null 2>&1; then
    sudo -u pioreactor -i pio config set camera use_ir_led 1 --shared
fi

sudo -u pioreactor -i pios sync-configs || :
