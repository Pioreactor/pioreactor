#!/bin/bash

set -xeu

export LC_ALL=C


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/50_self_test.yaml"
DESTINATION_DIR="/home/pioreactor/.pioreactor/ui/jobs"
DESTINATION="$DESTINATION_DIR/50_self_test.yaml"

if [ ! -f "$SOURCE" ] || [ ! -s "$SOURCE" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty self-test UI job descriptor update asset: $SOURCE"
    exit 1
fi

if ! grep -q '^job_name: self_test$' "$SOURCE"; then
    sudo -u pioreactor -i pio log -l ERROR -m "Invalid self-test UI job descriptor update asset: $SOURCE"
    exit 1
fi

install -d -o pioreactor -g www-data -m 0755 "$DESTINATION_DIR"

TEMP_FILE="$(mktemp "$DESTINATION_DIR/.50_self_test.yaml.XXXXXX")"
trap 'rm -f "$TEMP_FILE"' EXIT

install -o pioreactor -g www-data -m 0644 "$SOURCE" "$TEMP_FILE"
mv "$TEMP_FILE" "$DESTINATION"
trap - EXIT

if [ ! -s "$DESTINATION" ] || ! cmp -s "$SOURCE" "$DESTINATION"; then
    sudo -u pioreactor -i pio log -l ERROR -m "Failed to install self-test UI job descriptor: $DESTINATION"
    exit 1
fi
