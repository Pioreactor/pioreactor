#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # new gr params
    crudini --set /home/pioreactor/.pioreactor/config.ini growth_rate_kalman obs_std 1.0
    crudini --set /home/pioreactor/.pioreactor/config.ini growth_rate_kalman od_std 0.0025
    crudini --set /home/pioreactor/.pioreactor/config.ini growth_rate_kalman rate_std 0.25

    # change config's to add new stirring dodging behaviour
    crudini --set /home/pioreactor/.pioreactor/config.ini stirring.config target_rpm_during_od_reading 0
    crudini --set /home/pioreactor/.pioreactor/config.ini stirring.config target_rpm_outside_od_reading $(crudini --get /home/pioreactor/.pioreactor/config.ini stirring.config target_rpm)
    crudini --set /home/pioreactor/.pioreactor/config.ini stirring.config initial_target_rpm $(crudini --get /home/pioreactor/.pioreactor/config.ini stirring.config target_rpm)
    crudini --del /home/pioreactor/.pioreactor/config.ini stirring.config target_rpm


    # add raw od readings to export
    EXPORTABLE_DATASETS="/home/pioreactor/.pioreactor/exportable_datasets"
    su -u pioreactor cp "$SCRIPT_DIR"/27_raw_od_readings.yaml "$EXPORTABLE_DATASETS"
    echo "Added new 27_raw_od_readings.yaml"


fi
