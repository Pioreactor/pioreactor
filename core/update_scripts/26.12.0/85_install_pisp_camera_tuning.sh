#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION_DIR="/home/pioreactor/.pioreactor/camera"

# Install on every model so an SD card can move between Pi generations.
for name in ov5647_noir_200ms_pisp.json ov5647_noir_200ms_pisp.LICENSE; do
    test -s "$SCRIPT_DIR/$name"
done

install -d -o pioreactor -g www-data -m 0755 "$DESTINATION_DIR"
TEMP_FILE=""
trap 'rm -f "$TEMP_FILE"' EXIT
for name in ov5647_noir_200ms_pisp.json ov5647_noir_200ms_pisp.LICENSE; do
    TEMP_FILE="$(mktemp "$DESTINATION_DIR/.$name.XXXXXX")"
    install -o pioreactor -g www-data -m 0644 "$SCRIPT_DIR/$name" "$TEMP_FILE"
    mv "$TEMP_FILE" "$DESTINATION_DIR/$name"
    cmp -s "$SCRIPT_DIR/$name" "$DESTINATION_DIR/$name"
done
