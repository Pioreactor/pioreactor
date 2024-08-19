#!/bin/bash

set -xeu


export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    touch "$PIO_DIR/config_$HOSTNAME.ini" # create if it doesn't exist.

    crudini --ini-options=nospace --set "$PIO_DIR/config_$HOSTNAME.ini" cluster.topology leader_address 127.0.0.1 \
                                  --set "$PIO_DIR/config_$HOSTNAME.ini" mqtt broker_address 127.0.0.1


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


# change the permissions in the log file, and logrotate file
sudo chmod 666 /var/log/pioreactor.log
sudo sed -i 's/create 0660 pioreactor pioreactor/create 0666 pioreactor pioreactor/' /etc/logrotate.d/pioreactor


# update firmware to 0.3
sudo cp "$SCRIPT_DIR"/main.elf /usr/local/bin/main.elf || sudo wget https://github.com/Pioreactor/pico-build/releases/download/0.3/main.elf -o /usr/local/bin/main.elf
sudo systemctl restart load_rp2040.service || :
