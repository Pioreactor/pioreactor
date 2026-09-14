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
