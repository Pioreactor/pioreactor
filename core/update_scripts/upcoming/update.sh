#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/30_add_camera_config.sh"
bash "$SCRIPT_DIR/40_install_self_test_ui_job.sh"
bash "$SCRIPT_DIR/60_migrate_plugin_ui_config.sh"
