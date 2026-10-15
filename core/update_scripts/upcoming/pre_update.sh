#!/bin/bash

set -xeu

export LC_ALL=C

# 26.11.0 supplies the broker and onboarding helper to existing workers.
min_version="26.11.0"
current_version=$(sudo -u pioreactor -i pio version)
is_valid=$(printf "%s\n%s" "$current_version" "$min_version" | sort -V | head -n1)
if [ "$is_valid" != "$min_version" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Update to $min_version before installing this release."
    exit 1
fi
