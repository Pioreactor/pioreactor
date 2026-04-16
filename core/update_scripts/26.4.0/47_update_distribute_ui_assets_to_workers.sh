#!/bin/bash

set -xeu

export LC_ALL=C

CONFIG=/home/pioreactor/.pioreactor/config.ini
CRUDINI=/opt/pioreactor/venv/bin/crudini
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$("$CRUDINI" --get "$CONFIG" cluster.topology leader_hostname)
UI_ROOT=/home/pioreactor/.pioreactor/ui
RSYNC_TIMEOUT=15
SSH_CONNECT_TIMEOUT=5

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    echo "Skipping UI distribution on non-leader $HOSTNAME."
    exit 0
fi

if [ ! -d "$UI_ROOT" ]; then
    echo "Skipping UI distribution because $UI_ROOT does not exist."
    exit 0
fi

while IFS= read -r worker; do
    worker=$(echo "$worker" | xargs)
    [ -n "$worker" ] || continue
    [ "$worker" = "$LEADER_HOSTNAME" ] && continue

    address=$("$CRUDINI" --get "$CONFIG" cluster.addresses "$worker" 2>/dev/null || :)
    address=$(echo "$address" | xargs)
    [ -n "$address" ] || continue

    if ! sudo -u pioreactor -i rsync \
        -az \
        --checksum \
        --timeout "$RSYNC_TIMEOUT" \
        -e "ssh -o ConnectTimeout=$SSH_CONNECT_TIMEOUT" \
        --rsync-path "mkdir -p '$UI_ROOT' && rsync" \
        "$UI_ROOT/" \
        "pioreactor@$address:$UI_ROOT/"; then
        sudo -u pioreactor -i pio log -l WARNING -m "Unable to distribute UI assets to $worker at $address during update."
    fi
done < <(
    "$CRUDINI" --get "$CONFIG" cluster.addresses || :
)
