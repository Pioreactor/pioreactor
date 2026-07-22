#!/bin/bash

set -xeu

export LC_ALL=C

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

if sudo -u pioreactor -i pio config get ui.features camera --shared >/dev/null 2>&1; then
    exit 0
fi

sudo -u pioreactor -i pio config set ui.features camera 0 --shared
