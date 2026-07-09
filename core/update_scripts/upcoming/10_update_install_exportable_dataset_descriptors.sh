#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
EXPORTABLE_DATASETS_DIR="$DOT_PIOREACTOR/exportable_datasets"
tmp=""

clean_up() {
    if [ -n "$tmp" ]; then
        rm -f "$tmp"
    fi
}

trap clean_up EXIT

require_descriptor_asset() {
    local path="$1"
    local dataset_name="$2"

    [ -f "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Missing exportable dataset descriptor update asset: $path"
        exit 1
    }
    [ -s "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Empty exportable dataset descriptor update asset: $path"
        exit 1
    }
    grep -q "^dataset_name: $dataset_name$" "$path" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Exportable dataset descriptor has wrong dataset_name: $path"
        exit 1
    }
    grep -q "^column_descriptions:$" "$path" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Exportable dataset descriptor is missing column_descriptions: $path"
        exit 1
    }
}

install_descriptor() {
    local filename="$1"
    local dataset_name="$2"
    local src="$SCRIPT_DIR/$filename"
    local dst="$EXPORTABLE_DATASETS_DIR/$filename"

    require_descriptor_asset "$src" "$dataset_name"

    install -d -o pioreactor -g www-data -m 2775 "$EXPORTABLE_DATASETS_DIR"
    tmp="$(mktemp "$EXPORTABLE_DATASETS_DIR/.${filename}.XXXXXX")"
    install -o pioreactor -g www-data -m 0664 "$src" "$tmp"
    mv "$tmp" "$dst"
    tmp=""

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
    grep -q "^dataset_name: $dataset_name$" "$dst" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst has wrong dataset_name"
        exit 1
    }
}

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

install_descriptor 00_pioreactor_unit_activity_data.yaml pioreactor_unit_activity_data
install_descriptor 01_logs.yaml logs
install_descriptor 01_od_readings.yaml od_readings
install_descriptor 02_od_readings_filtered.yaml od_readings_filtered
install_descriptor 03_growth_rates.yaml growth_rates
install_descriptor 03_liquid_volumes.yaml liquid_volumes
install_descriptor 04_experiments.yaml experiments
install_descriptor 05_dosing_events.yaml dosing_events
install_descriptor 06_led_change_events.yaml led_change_events
install_descriptor 10_dosing_automation_settings.yaml dosing_automation_settings
install_descriptor 11_led_automation_settings.yaml led_automation_settings
install_descriptor 12_temperature_automation_settings.yaml temperature_automation_settings
install_descriptor 14_temperature_readings.yaml temperature_readings
install_descriptor 15_stirring_rates.yaml stirring_rates
install_descriptor 18_ir_led_intensities.yaml ir_led_intensities
install_descriptor 19_pioreactor_unit_labels.yaml pioreactor_unit_labels
install_descriptor 20_temperature_automation_events.yaml temperature_automation_events
install_descriptor 21_dosing_automation_events.yaml dosing_automation_events
install_descriptor 22_led_automation_events.yaml led_automation_events
install_descriptor 24_pioreactor_unit_activity_data_rollup.yaml pioreactor_unit_activity_data_rollup
install_descriptor 25_calibrations.yaml calibrations
install_descriptor 26_pwm_dcs.yaml pwm_dcs
install_descriptor 27_raw_od_readings.yaml raw_od_readings
install_descriptor 28_od_readings_fused.yaml od_readings_fused
install_descriptor 30_alt_media_fractions.yaml alt_media_fractions
