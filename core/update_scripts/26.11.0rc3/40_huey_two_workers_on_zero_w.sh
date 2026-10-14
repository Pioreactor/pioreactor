#!/bin/bash

set -xeu

export LC_ALL=C

# Calibration steps now run as a Huey task that waits on other Huey tasks
# (hardware actions), so every consumer needs at least two workers. Only the
# Zero W worker profile ran one.
LAUNCHER=/usr/local/bin/start_pioreactor_huey.sh

[ -f "$LAUNCHER" ] || exit 0

sed -E -i '/huey_consumer/ s/(^|[[:space:]])-w[[:space:]]+1([[:space:]]|$)/\1-w 2\2/' "$LAUNCHER"

if grep -Eq 'huey_consumer.*[[:space:]]-w[[:space:]]+1([[:space:]]|$)' "$LAUNCHER"; then
    echo "Unable to set two Huey workers in $LAUNCHER." >&2
    exit 1
fi
