#!/bin/bash

set -xeu

export LC_ALL=C

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    DATABASE=$(sudo -u pioreactor -i pio config get storage database)
    test -f "$DATABASE"
    # SQLite has no ADD COLUMN IF NOT EXISTS. Leave historical geometry unknown.
    HAS_ANGLE=$(sudo -u pioreactor -i sqlite3 "$DATABASE" "SELECT count(*) FROM pragma_table_info('raw_od_readings') WHERE name='angle';")
    if [ "$HAS_ANGLE" = "0" ]; then
        sudo -u pioreactor -i sqlite3 -bail -cmd '.timeout 60000' "$DATABASE" \
            'ALTER TABLE raw_od_readings ADD COLUMN angle INTEGER;'
    fi
    chown pioreactor:www-data "$DATABASE"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/10_install_od_defaults.sh"

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
