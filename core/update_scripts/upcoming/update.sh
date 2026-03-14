#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(/opt/pioreactor/venv/bin/crudini --get "$CONFIG" cluster.topology leader_hostname)

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

    require_nonempty_asset "$src"

    local tmp
    tmp="$(mktemp)"
    install -o pioreactor -g pioreactor -m 0644 "$src" "$tmp"
    install -d -o pioreactor -g pioreactor -m 0755 "$(dirname "$dst")"
    mv "$tmp" "$dst"

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
}

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    install_checked_asset \
        "$SCRIPT_DIR/50_self_test.yaml" \
        "$DOT_PIOREACTOR/ui/jobs/50_self_test.yaml"
fi
