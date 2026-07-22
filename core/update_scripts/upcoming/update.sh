#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_update_install_exportable_dataset_descriptors.sh"
bash "$SCRIPT_DIR/20_migrate_experiment_profile_versions.sh"
bash "$SCRIPT_DIR/30_add_camera_ui_feature_flag.sh"
