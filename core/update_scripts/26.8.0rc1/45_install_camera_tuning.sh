#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_JSON="$SCRIPT_DIR/ov5647_noir_200ms.json"
SOURCE_LICENSE="$SCRIPT_DIR/ov5647_noir_200ms.LICENSE"
DESTINATION_DIR="/home/pioreactor/.pioreactor/camera"
DESTINATION_JSON="$DESTINATION_DIR/ov5647_noir_200ms.json"
DESTINATION_LICENSE="$DESTINATION_DIR/ov5647_noir_200ms.LICENSE"

if [ ! -f "$SOURCE_JSON" ] || [ ! -s "$SOURCE_JSON" ] || \
    [ ! -f "$SOURCE_LICENSE" ] || [ ! -s "$SOURCE_LICENSE" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty camera tuning update asset."
    exit 1
fi

if ! printf '%s  %s\n%s  %s\n' \
    "2901955f62c672991c078bf04108215cd0d36c198fae6687751467a0bb240836" "$SOURCE_JSON" \
    "345832e54372edc54eaaf112719c9ed7e61dd41514354941df261bf020f3e5c8" "$SOURCE_LICENSE" \
    | sha256sum --check --status; then
    sudo -u pioreactor -i pio log -l ERROR -m "Invalid camera tuning update asset checksum."
    exit 1
fi

install -d -o pioreactor -g www-data -m 0755 "$DESTINATION_DIR"

TEMP_JSON="$(mktemp "$DESTINATION_DIR/.ov5647_noir_200ms.json.XXXXXX")"
TEMP_LICENSE="$(mktemp "$DESTINATION_DIR/.ov5647_noir_200ms.LICENSE.XXXXXX")"
trap 'rm -f "$TEMP_JSON" "$TEMP_LICENSE"' EXIT

install -o pioreactor -g www-data -m 0644 "$SOURCE_JSON" "$TEMP_JSON"
install -o pioreactor -g www-data -m 0644 "$SOURCE_LICENSE" "$TEMP_LICENSE"
mv "$TEMP_LICENSE" "$DESTINATION_LICENSE"
mv "$TEMP_JSON" "$DESTINATION_JSON"
trap - EXIT

if [ ! -s "$DESTINATION_JSON" ] || [ ! -s "$DESTINATION_LICENSE" ] || \
    ! cmp -s "$SOURCE_JSON" "$DESTINATION_JSON" || \
    ! cmp -s "$SOURCE_LICENSE" "$DESTINATION_LICENSE"; then
    sudo -u pioreactor -i pio log -l ERROR -m "Failed to install camera tuning assets: $DESTINATION_DIR"
    exit 1
fi
