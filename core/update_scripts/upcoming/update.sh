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
ASSET="$SCRIPT_DIR/ui_settings_13_pwms.yaml"
SETTINGS_DIR=/home/pioreactor/.pioreactor/ui/settings

# Both leaders and workers serve settings descriptors. Install the new topic
# descriptor on every unit; there is no legacy pin-keyed telemetry support.
if [ ! -f "$ASSET" ] || [ ! -s "$ASSET" ] || ! grep -q '  - key: channel_dc' "$ASSET"; then
    sudo -u pioreactor -i pio log -l ERROR -m "Missing or invalid PWM settings update asset: $ASSET"
    exit 1
fi

install -d -o pioreactor -g www-data -m 2775 "$SETTINGS_DIR"
TMP_DESCRIPTOR="$(mktemp "$SETTINGS_DIR/.13_pwms.yaml.XXXXXX")"
trap 'rm -f "$TMP_DESCRIPTOR"' EXIT
install -o pioreactor -g www-data -m 0664 "$ASSET" "$TMP_DESCRIPTOR"
mv "$TMP_DESCRIPTOR" "$SETTINGS_DIR/13_pwms.yaml"
cmp "$ASSET" "$SETTINGS_DIR/13_pwms.yaml"

bash "$SCRIPT_DIR/20_install_bootfs_plugins.sh"

bash "$SCRIPT_DIR/30_install_bootfs_files.sh"
