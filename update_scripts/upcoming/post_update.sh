#!/bin/bash

set -x
set -e

export LC_ALL=C



PIO_DIR=/home/pioreactor/.pioreactor

# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_ADDRESS=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_address)

if [ "$HOSTNAME.local" = "$LEADER_ADDRESS" ]; then

    # we've added the new database tables, let's populate them.
    # 1. we add workers from the config to workers
    if crudini --get $PIO_DIR/config.ini cluster.inventory &>/dev/null; then
        units=$(crudini --get $PIO_DIR/config.ini cluster.inventory)

        # Iterate over each unit and insert it into the database
        while IFS= read -r unit; do
          sqlite3 $DB_FILE "INSERT OR IGNORE INTO workers (pioreactor_unit, added_at, is_active) VALUES ('$unit', STRFTIME('%Y-%m-%dT%H:%M:%f000Z', 'NOW'), 1);"
        done <<< "$units"

        # 2. we assign the workers to the current experiment
        sqlite3 $DB_FILE "INSERT INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) SELECT pioreactor_unit, experiment, added_at FROM workers JOIN latest_experiment;"
    else
        echo "No units defined in cluster.inventory"
        # Handle the case where no units are defined, if necessary
    fi
fi
