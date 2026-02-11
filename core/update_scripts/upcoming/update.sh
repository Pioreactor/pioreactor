#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(/opt/pioreactor/venv/crudini --get "$CONFIG" cluster.topology leader_hostname)

# UI automation definitions are leader-facing, so only install on the leader.
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    install -d -o pioreactor -g pioreactor -m 0755 "$DOT_PIOREACTOR/ui/automations/dosing"
    install -o pioreactor -g pioreactor -m 0644 \
        "$SCRIPT_DIR/turbidostat.yaml" \
        "$DOT_PIOREACTOR/ui/automations/dosing/turbidostat.yaml"
fi
