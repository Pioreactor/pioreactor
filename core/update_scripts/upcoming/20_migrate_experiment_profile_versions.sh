#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
EXPERIMENT_PROFILES_DIR="$DOT_PIOREACTOR/experiment_profiles"

if [ ! -d "$EXPERIMENT_PROFILES_DIR" ]; then
    exit 0
fi

for profile in "$EXPERIMENT_PROFILES_DIR"/*.yaml "$EXPERIMENT_PROFILES_DIR"/*.yml; do
    [ -s "$profile" ] || continue
    grep -q '^version:' "$profile" && continue

    tmp="$(mktemp "$EXPERIMENT_PROFILES_DIR/.experiment-profile.XXXXXX")"
    printf 'version: "1.0"\n\n' > "$tmp"
    cat "$profile" >> "$tmp"

    chown pioreactor:www-data "$tmp"
    chmod 0664 "$tmp"
    mv "$tmp" "$profile"
done
