#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_huey_idle_polling_backoff.sh"
bash "$SCRIPT_DIR/20_ir_led_intensity_auto_to_80.sh"
bash "$SCRIPT_DIR/30_od_samples_per_second_to_seconds_between_readings.sh"
bash "$SCRIPT_DIR/40_stirring_remove_target_rpm_outside_od_reading.sh"
bash "$SCRIPT_DIR/50_mdns_skip_unicast_soa_check.sh"
bash "$SCRIPT_DIR/60_update_ca_certificates.sh"
bash "$SCRIPT_DIR/70_remove_circulation.sh"
bash "$SCRIPT_DIR/75_disable_spa_shell_cache_on_all_units.sh"
bash "$SCRIPT_DIR/80_cache_hashed_assets_immutable.sh"
bash "$SCRIPT_DIR/85_install_pisp_camera_tuning.sh"

bash "$SCRIPT_DIR/90_browser_mqtt_proxy.sh"
