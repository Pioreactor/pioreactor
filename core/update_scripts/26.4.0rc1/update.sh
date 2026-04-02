#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_update_install_cli_wrappers.sh"
bash "$SCRIPT_DIR/20_update_migrate_bioreactor_volume_key.sh"
bash "$SCRIPT_DIR/30_update_install_plugin_helpers.sh"
bash "$SCRIPT_DIR/40_repair_plugin_descriptors.sh"
