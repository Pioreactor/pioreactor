#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    DB_PATH=$(crudini --get /home/pioreactor/.pioreactor/config.ini storage database)
    CONFIG_DIR="/home/pioreactor/.pioreactor"

    # Loop through config files in the directory
    for config_file in "$CONFIG_DIR"/config_*.ini; do
        if [[ -f "$config_file" ]]; then
            pioreactor_unit=$(basename "$config_file" | sed 's/config_\(.*\)\.ini/\1/')
            model_name=$(crudini --get "$config_file" pioreactor model 2>/dev/null)
            model_version=$(crudini --get "$config_file" pioreactor version 2>/dev/null)

            if [[ -n "$model_name" && -n "$model_version" ]]; then
                sqlite3 "$DB_PATH" <<EOF
UPDATE workers SET
    model_name = '$model_name',
    model_version = '$model_version'
WHERE pioreactor_unit = '$pioreactor_unit';
EOF
                echo "Updated: $pioreactor_unit ($model_name, $model_version)"
                crudini --del "$config_file" pioreactor
            else
                echo "Skipping $config_file: Missing model or version"
            fi
        fi
    done
    sudo -u pioreactor pios sync-configs || :
fi
