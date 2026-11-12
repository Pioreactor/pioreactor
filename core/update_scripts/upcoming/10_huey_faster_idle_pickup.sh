#!/bin/bash

set -xeu

export LC_ALL=C

# 26.12.0 let idle standard-profile Huey workers back off to 100 ms polling. That added up to ~100 ms
# of pickup latency to every leader fan-out read (and its chord callback). Cap the backoff at 20 ms:
# measured on a 10x Pi 3B cluster, broadcast GETs went from ~180-200 ms median (p90 ~330-360 ms)
# to ~145 ms median (p90 ~190-220 ms).
LAUNCHER=/usr/local/bin/start_pioreactor_huey.sh

[ -f "$LAUNCHER" ] || exit 0

sed -E -i '/huey_consumer.*-d 0\.01/ s/(^|[[:space:]])-m[[:space:]]+0\.1([[:space:]]|$)/\1-m 0.02\2/' "$LAUNCHER"

if grep -Eq 'huey_consumer.*[[:space:]]-m[[:space:]]+0\.1[[:space:]].*-d 0\.01' "$LAUNCHER"; then
    echo "Unable to set Huey idle polling backoff cap in $LAUNCHER." >&2
    exit 1
fi
