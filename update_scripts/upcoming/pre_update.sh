#!/bin/bash

set -xeu


export LC_ALL=C

# Lower bound version
min_version="24.12.5"

# Get the current version of pio
current_version=$(sudo -u pioreactor pio version)

# Use sorting to determine if the current version is less than the minimum version
is_valid=$(printf "%s\n%s" "$current_version" "$min_version" | sort -V | head -n1)

# If the smallest version isn't the minimum version, then current version is too low
if [ "$is_valid" != "$min_version" ]; then
    sudo -u pioreactor pio log -l ERROR -m "Version error: installed version $current_version is lower than the minimum required version $min_version."
    exit 1
fi

echo "Version check passed: $current_version"



LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)


# we need this config for downstream updates, so set it now.
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    crudini  --set /home/pioreactor/.pioreactor/config.ini storage temporary_cache /tmp/pioreactor_cache/local_intermittent_pioreactor_metadata.sqlite \
             --set /home/pioreactor/.pioreactor/config.ini storage persistent_cache /home/pioreactor/.pioreactor/storage/local_persistent_pioreactor_metadata.sqlite

    sudo -u pioreactor pios sync-configs --shared || :

fi
