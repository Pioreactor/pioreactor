#!/bin/bash

set -xeu


export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor

# all pioreactors get a unit_config, include leader-only pioworekrs
touch $PIO_DIR/unit_config.ini


HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # stirring -> stirring.config
    # Iterate over each ini file in the directory
    for ini_file in "$PIO_DIR"/config*.ini; do

      echo "Processing file: $ini_file"

      # Check if the [stirring] section exists in the file
      if crudini --get "$ini_file" stirring &> /dev/null; then
        echo "Found [stirring] section in $ini_file. Changing to [stirring.config]."

        # Create a temporary file to work with
        tmp_file=$(mktemp)
        echo "[stirring.config]" >> "$tmp_file"
        crudini --format=sh --get "$ini_file" stirring  >> "$tmp_file"

        # Use crudini to rename the section
        crudini --merge "$ini_file"  <  "$tmp_file"

        # Replace the original file with the updated file
        #mv "$tmp_file" "$ini_file"

        # Optionally remove the original [stirring] section
        crudini --del "$ini_file" stirring

      else
        echo "No [stirring] section found in $ini_file. Skipping."
      fi
    done


    # od_config -> od_reading.config
    # Iterate over each ini file in the directory
    for ini_file in "$PIO_DIR"/config*.ini; do

      echo "Processing file: $ini_file"

      # Check if the [od_config] section exists in the file
      if crudini --get "$ini_file" od_config &> /dev/null; then
        echo "Found [od_config] section in $ini_file. Changing to [od_reading.config]."

        # Create a temporary file to work with
        tmp_file=$(mktemp)
        echo "[od_reading.config]" >> "$tmp_file"
        crudini --format=sh --get "$ini_file" od_config  >> "$tmp_file"

        # Use crudini to rename the section
        crudini --merge "$ini_file"  <  "$tmp_file"

        # Replace the original file with the updated file
        #mv "$tmp_file" "$ini_file"

        # Optionally remove the original [od_config] section
        crudini --del "$ini_file" od_config

      else
        echo "No [od_config] section found in $ini_file. Skipping."
      fi
    done

    sudo -u pioreactor pios sync-configs
fi
