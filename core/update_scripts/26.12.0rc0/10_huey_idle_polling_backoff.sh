#!/bin/bash

set -xeu

export LC_ALL=C

# The standard Huey profile polled its queue every 10 ms with no backoff, so ten idle
# workers ran about 1000 queue checks per second. Let idle workers back off to 100 ms;
# a worker returns to 10 ms polling as soon as it picks up a task.
LAUNCHER=/usr/local/bin/start_pioreactor_huey.sh

[ -f "$LAUNCHER" ] || exit 0

sed -E -i '/huey_consumer.*-d 0\.01/ s/(^|[[:space:]])-b[[:space:]]+1\.0([[:space:]]|$)/\1-b 1.15 -m 0.1\2/' "$LAUNCHER"

if grep -Eq 'huey_consumer.*[[:space:]]-b[[:space:]]+1\.0[[:space:]].*-d 0\.01' "$LAUNCHER"; then
    echo "Unable to set Huey idle polling backoff in $LAUNCHER." >&2
    exit 1
fi
