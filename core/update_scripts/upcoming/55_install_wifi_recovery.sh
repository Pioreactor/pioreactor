#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_nonempty_asset() {
    local path="$1"
    if [ ! -f "$path" ] || [ ! -s "$path" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty Wi-Fi recovery asset: $path"
        exit 1
    fi
}

install_checked_asset() {
    local src="$1"
    local dst="$2"
    local mode="$3"
    local tmp

    require_nonempty_asset "$src"
    tmp="$(mktemp)"
    install -o root -g root -m "$mode" "$src" "$tmp"
    install -d -o root -g root -m 0755 "$(dirname "$dst")"
    mv "$tmp" "$dst"
    [ -s "$dst" ]
}

install_checked_asset \
    "$SCRIPT_DIR/wifi_recovery.sh" \
    /usr/local/bin/pioreactor-wifi-recovery.sh \
    0755
install_checked_asset \
    "$SCRIPT_DIR/pioreactor-wifi-recovery.service" \
    /etc/systemd/system/pioreactor-wifi-recovery.service \
    0644
install_checked_asset \
    "$SCRIPT_DIR/pioreactor-wifi-recovery.timer" \
    /etc/systemd/system/pioreactor-wifi-recovery.timer \
    0644

systemctl daemon-reload
systemctl enable --now pioreactor-wifi-recovery.timer
systemctl is-enabled --quiet pioreactor-wifi-recovery.timer
