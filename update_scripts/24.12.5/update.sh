#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the hostname
HOSTNAME=$(hostname)

# Get the leader hostname
# Don't use `leader_address`, as users do change that.
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    crudini  --set /home/pioreactor/.pioreactor/config.ini cluster_addresses \
             --set /home/pioreactor/.pioreactor/config.ini stirring.config post_delay_duration 0.25 \
             --set /home/pioreactor/.pioreactor/config.ini stirring.config pre_delay_duration 1.50 \
             --set /home/pioreactor/.pioreactor/config.ini stirring.config enable_dodging_od False


    sudo -u pioreactor mkdir -p /home/pioreactor/.pioreactor/exportable_datasets
    sudo -u pioreactor mkdir -p /home/pioreactor/.pioreactor/plugins/exportable_datasets

    # Unzip datasets.zip into the exportable_datasets directory
    DATASETS_ZIP="$SCRIPT_DIR/datasets.zip"
    if [ -f "$DATASETS_ZIP" ]; then
        sudo -u pioreactor unzip -o "$DATASETS_ZIP" -d /home/pioreactor/.pioreactor/exportable_datasets
    else
        echo "Error: datasets.zip not found in $SCRIPT_DIR" >&2
        exit 1
    fi

    sudo -u pioreactor pios sync-configs --shared || :

fi

cp "$SCRIPT_DIR/install_pioreactor_plugin.sh" /usr/local/bin/install_pioreactor_plugin.sh
cp "$SCRIPT_DIR/uninstall_pioreactor_plugin.sh" /usr/local/bin/uninstall_pioreactor_plugin.sh
