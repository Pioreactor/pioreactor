#!/bin/bash

set -xeu

export LC_ALL=C

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

while read -r option default; do
    if ! sudo -u pioreactor -i pio config get camera "$option" --shared >/dev/null 2>&1; then
        sudo -u pioreactor -i pio config set camera "$option" "$default" --shared
    fi
done <<'EOF'
enabled 0
snapshot_interval_minutes 5
keep_camera_active 0
ir_led_intensity 80
capture_backend rpicam
camera_index 0
device_path /dev/video0
EOF

sudo -u pioreactor -i pios sync-configs
