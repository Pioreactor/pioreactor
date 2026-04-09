#!/bin/bash

set -xeu

export LC_ALL=C

CONFIG=/home/pioreactor/.pioreactor/config.ini
CRUDINI=/opt/pioreactor/venv/bin/crudini
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$("$CRUDINI" --get "$CONFIG" cluster.topology leader_hostname)
HELPER_SRC="$SCRIPT_DIR/add_new_pioreactor_worker_from_leader.sh"
HELPER_DST=/usr/local/bin/add_new_pioreactor_worker_from_leader.sh

require_nonempty_asset() {
    local path="$1"
    [ -f "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Missing update asset: $path"
        exit 1
    }
    [ -s "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Empty update asset: $path"
        exit 1
    }
}

install_checked_asset() {
    local src="$1"
    local dst="$2"
    local owner="$3"
    local group="$4"
    local mode="$5"

    require_nonempty_asset "$src"

    local tmp
    tmp="$(mktemp)"
    install -o "$owner" -g "$group" -m "$mode" "$src" "$tmp"
    install -d -o "$owner" -g "$group" -m 0755 "$(dirname "$dst")"
    mv "$tmp" "$dst"

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
    [ -x "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is not executable"
        exit 1
    }
}

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    echo "Skipping $HELPER_DST install on non-leader $HOSTNAME."
    exit 0
fi

install_checked_asset "$HELPER_SRC" "$HELPER_DST" root root 0755
