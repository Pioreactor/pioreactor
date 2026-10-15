#!/bin/bash

set -xeu

export LC_ALL=C

# Adding a worker used to append `server <leader> iburst prefer` to chrony.conf, once per add.
# `pio cluster join` now owns a drop-in instead, so move the most recent line there.
# Leaders, and workers added since, have no such line.
CHRONY_CONFIG=/etc/chrony/chrony.conf
LEADER_SOURCE=/etc/chrony/conf.d/pioreactor-leader.conf
LEGACY_LINE='^server [^ ]+ iburst prefer$'

[ -f "$CHRONY_CONFIG" ] || exit 0
grep -Eq "$LEGACY_LINE" "$CHRONY_CONFIG" || exit 0

grep -E "$LEGACY_LINE" "$CHRONY_CONFIG" | tail -n 1 > "$LEADER_SOURCE"
sed -E -i "/$LEGACY_LINE/d" "$CHRONY_CONFIG"
