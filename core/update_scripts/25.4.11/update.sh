#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # new add_worker script
    ADD_WORKER_FILE="/usr/local/bin/add_new_pioreactor_worker_from_leader.sh"
    sudo cp "$SCRIPT_DIR"/add_new_pioreactor_worker_from_leader.sh $ADD_WORKER_FILE
    echo "Added new add_new_pioreactor_worker_from_leader.sh."

    # change config's ui.overview.cards to rename and add new entry
    crudini --set /home/pioreactor/.pioreactor/config.ini ui.overview.charts optical_density 1
    crudini --set /home/pioreactor/.pioreactor/config.ini ui.overview.charts raw_optical_density 0

    # remove unused config
    crudini --del /home/pioreactor/.pioreactor/config.ini dosing_automation.config max_volume_to_stop

    DB_PATH=$(crudini --get /home/pioreactor/.pioreactor/config.ini storage database)

    sqlite3 "$DB_PATH" <<EOF
CREATE TABLE IF NOT EXISTS raw_od_readings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL NOT NULL,
    channel INTEGER CHECK (channel IN (1, 2)) NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS raw_od_readings_ix
ON raw_od_readings (experiment, pioreactor_unit, timestamp);
EOF

    sqlite3 "$DB_PATH" "ALTER TABLE workers ADD COLUMN model_version TEXT;" || true
    sqlite3 "$DB_PATH" "ALTER TABLE workers ADD COLUMN model_name TEXT;" || true


fi

# fix any calibration / persistent cache permission issues
sudo chown pioreactor:www-data /home/pioreactor/.pioreactor/storage
sudo chmod g+srwx /home/pioreactor/.pioreactor/storage
