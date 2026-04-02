#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo -u pioreactor -i /opt/pioreactor/venv/bin/python "$SCRIPT_DIR/repair_plugin_descriptors.py" sync-from-leader
