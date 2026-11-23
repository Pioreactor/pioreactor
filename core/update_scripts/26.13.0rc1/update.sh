#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_huey_faster_idle_pickup.sh"
bash "$SCRIPT_DIR/20_standalone_config.sh"

# Older Raspberry Pi images installed this helper with mode 0644.
if [ -f /usr/local/bin/bootfs_plugins.sh ]; then
    chmod 0755 /usr/local/bin/bootfs_plugins.sh
fi
