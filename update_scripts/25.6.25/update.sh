#!/bin/bash

set -xeu


export LC_ALL=C

CONFIG=/home/pioreactor/.pioreactor/config.ini
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get "$CONFIG" cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # new gr params
    crudini --set "$CONFIG" growth_rate_kalman obs_std 1.0
    crudini --set "$CONFIG" growth_rate_kalman od_std 0.0025
    crudini --set "$CONFIG" growth_rate_kalman rate_std 0.25


    crudini --set "$CONFIG" stirring.config target_rpm_during_od_reading 0

    if ! crudini --get "$CONFIG" stirring.config target_rpm_outside_od_reading &>/dev/null; then
        val=$(crudini --get "$CONFIG" stirring.config target_rpm 2>/dev/null || echo "500")
        crudini --set "$CONFIG" stirring.config target_rpm_outside_od_reading "$val"
    fi

    if ! crudini --get "$CONFIG" stirring.config initial_target_rpm &>/dev/null; then
        val=$(crudini --get "$CONFIG" stirring.config target_rpm 2>/dev/null || echo "500")
        crudini --set "$CONFIG" stirring.config initial_target_rpm "$val"
    fi
    crudini --del "$CONFIG" stirring.config target_rpm || :

    # update max_volume_ml to max_working_volume_ml
    if ! crudini --get "$CONFIG" bioreactor max_working_volume_ml &>/dev/null; then
        val=$(crudini --get "$CONFIG" bioreactor max_volume_ml 2>/dev/null || echo "20")
        crudini --set "$CONFIG" bioreactor max_working_volume_ml "$val"
    fi
    crudini --del "$CONFIG" bioreactor max_volume_ml || :

    # experimental pump malfunction
    crudini --set "$CONFIG" dosing_automation.config experimental_detect_pump_malfunction false
    crudini --set "$CONFIG" dosing_automation.config experimental_pump_malfunction_tolerance 0.2


    # add raw od readings to export
    EXPORTABLE_DATASETS="/home/pioreactor/.pioreactor/exportable_datasets"
    sudo -u pioreactor cp -n "$SCRIPT_DIR"/27_raw_od_readings.yaml "$EXPORTABLE_DATASETS"
    echo "Added new 27_raw_od_readings.yaml"

fi
