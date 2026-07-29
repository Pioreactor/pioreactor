#!/bin/bash

set -xeu


export LC_ALL=C

# Lower bound version
min_version="26.1.30"

# Get the current version of pio
current_version=$(sudo -u pioreactor -i pio version)

# Use sorting to determine if the current version is less than the minimum version
is_valid=$(printf "%s\n%s" "$current_version" "$min_version" | sort -V | head -n1)

# If the smallest version isn't the minimum version, then current version is too low
if [ "$is_valid" != "$min_version" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Version error: installed version $current_version is lower than the minimum required version $min_version."
    exit 1
fi

echo "Version check passed: $current_version"
