#!/bin/bash

set -xeu
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIO_DIR=/home/pioreactor/.pioreactor
STANDALONE_CONFIG="$PIO_DIR/config.ini.standalone"
TEMPLATE="$SCRIPT_DIR/config.example.ini"
WORKER_SETUP="$SCRIPT_DIR/add_new_pioreactor_worker_from_leader.sh"
LEADER_CONDITION="$SCRIPT_DIR/pioreactor-leader-only.conf"

test -s "$TEMPLATE"
grep -Fxq '[cluster.topology]' "$TEMPLATE"
test -s "$WORKER_SETUP"
test -s "$LEADER_CONDITION"

config_tmp=""
setup_tmp=""
condition_tmp=""
trap 'rm -f -- "$config_tmp" "$setup_tmp" "$condition_tmp"' EXIT

# Older versions of this helper write directly to the worker's live config.
setup_tmp="$(mktemp /usr/local/bin/.worker-setup.XXXXXX)"
install -o root -g root -m 0755 "$WORKER_SETUP" "$setup_tmp"
mv -f "$setup_tmp" /usr/local/bin/add_new_pioreactor_worker_from_leader.sh

# Seed leader-capable units, so one that already joined another cluster can return to standalone.
# The next successful join from standalone saves its live edits here.
if systemctl is-enabled --quiet pioreactor-leader.target && [ ! -e "$STANDALONE_CONFIG" ]; then
    config_tmp="$(mktemp "$PIO_DIR/.standalone-config.XXXXXX")"
    install -o pioreactor -g www-data -m 0664 "$TEMPLATE" "$config_tmp"
    mv -n "$config_tmp" "$STANDALONE_CONFIG"
fi

# The provisioned targets stay enabled so a leader-worker can return to standalone.
# Gate the leader-only processes on the current role when they next start.
for service in pioreactor_startup_run@mqtt_to_db_streaming.service backup-database.service avahi_aliases.service; do
    drop_in="/etc/systemd/system/$service.d"
    install -d -m 0755 "$drop_in"
    condition_tmp="$(mktemp "$drop_in/.leader-only.XXXXXX")"
    install -o root -g root -m 0644 "$LEADER_CONDITION" "$condition_tmp"
    mv -f "$condition_tmp" "$drop_in/10-pioreactor-leader-only.conf"
done
systemctl daemon-reload
