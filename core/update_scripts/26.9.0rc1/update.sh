#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/pioreactor.env
LARGE_TEMP_DIRECTORY=/var/tmp/pioreactor
tmp="$(mktemp "${ENV_FILE}.XXXXXX")"

clean_up() {
    if [ -n "$tmp" ]; then
        rm -f "$tmp"
    fi
}

trap clean_up EXIT

install -d -o pioreactor -g www-data -m 2770 "$LARGE_TEMP_DIRECTORY"

awk -v large_temp_directory="$LARGE_TEMP_DIRECTORY" '
    BEGIN {
        configured = 0
    }

    /^PIOREACTOR_LARGE_TMPDIR=/ {
        if (!configured) {
            print "PIOREACTOR_LARGE_TMPDIR=" large_temp_directory
            configured = 1
        }
        next
    }

    {
        print
    }

    END {
        if (!configured) {
            print "PIOREACTOR_LARGE_TMPDIR=" large_temp_directory
        }
    }
' "$ENV_FILE" > "$tmp"

chown root:root "$tmp"
chmod 0644 "$tmp"
mv "$tmp" "$ENV_FILE"
tmp=""

CAMERA_DIRECTORY=/home/pioreactor/.pioreactor/camera
if [ ! -f "$CAMERA_DIRECTORY/viewing.conf" ]; then
    test -f "$SCRIPT_DIR/viewing.conf"
    test -s "$SCRIPT_DIR/viewing.conf"
    install -d -o pioreactor -g www-data -m 0755 "$CAMERA_DIRECTORY"
    tmp="$(mktemp "$CAMERA_DIRECTORY/.viewing.conf.XXXXXX")"
    install -o pioreactor -g www-data -m 0644 "$SCRIPT_DIR/viewing.conf" "$tmp"
    mv "$tmp" "$CAMERA_DIRECTORY/viewing.conf"
    tmp=""
fi

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    BACKUP_TIMER=/etc/systemd/system/backup-database.timer
    if [ -f "$BACKUP_TIMER" ]; then
        # Back up monthly, without catching up on missed backups at startup.
        sed -i \
            -e 's/^Description=.*/Description=Monthly database backup/' \
            -e 's/^OnCalendar=.*/OnCalendar=*-*-01 00:00:00/' \
            -e 's/^Persistent=.*/Persistent=false/' \
            "$BACKUP_TIMER"
        systemctl daemon-reload
        systemctl try-restart backup-database.timer
    fi

    if ! sudo -u pioreactor -i pio config get camera use_ir_led --shared >/dev/null 2>&1; then
        sudo -u pioreactor -i pio config set camera use_ir_led 1 --shared
    fi

    sudo -u pioreactor -i pios sync-configs || :
fi

bash "$SCRIPT_DIR/10_update_install_exportable_dataset_descriptors.sh"
