#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_update_install_cli_wrappers.sh"
bash "$SCRIPT_DIR/20_update_migrate_bioreactor_volume_key.sh"
bash "$SCRIPT_DIR/30_update_install_plugin_helpers.sh"
bash "$SCRIPT_DIR/40_repair_plugin_descriptors.sh"
bash "$SCRIPT_DIR/45_update_install_ui_job_assets.sh"
bash "$SCRIPT_DIR/46_update_install_add_worker_helper.sh"
bash "$SCRIPT_DIR/47_update_distribute_ui_assets_to_workers.sh"
