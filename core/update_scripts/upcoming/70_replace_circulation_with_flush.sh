#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOT_PIOREACTOR="/home/pioreactor/.pioreactor"

# Remove only the retired built-in descriptors, on leaders and workers.
rm -f "$DOT_PIOREACTOR/ui/jobs/14_circulate_media.yaml" \
      "$DOT_PIOREACTOR/ui/jobs/15_circulate_alt_media.yaml"

LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
if [ "$(hostname)" = "$LEADER_HOSTNAME" ]; then
    PROFILE_DIR="$DOT_PIOREACTOR/experiment_profiles"
    # Preserve an existing user profile, including on retries.
    if [ ! -e "$PROFILE_DIR/flush.yaml" ]; then
        [ -f "$SCRIPT_DIR/flush.yaml" ]
        [ -s "$SCRIPT_DIR/flush.yaml" ]
        install -d -o pioreactor -g www-data -m 0755 "$PROFILE_DIR"
        TMP_PROFILE=$(mktemp "$PROFILE_DIR/.flush.XXXXXX")
        trap 'rm -f "$TMP_PROFILE"' EXIT
        install -o pioreactor -g www-data -m 0644 "$SCRIPT_DIR/flush.yaml" "$TMP_PROFILE"
        mv "$TMP_PROFILE" "$PROFILE_DIR/flush.yaml"
        [ -s "$PROFILE_DIR/flush.yaml" ]
    fi
fi
