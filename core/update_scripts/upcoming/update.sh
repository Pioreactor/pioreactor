#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSET="$SCRIPT_DIR/ui_settings_13_pwms.yaml"
SETTINGS_DIR=/home/pioreactor/.pioreactor/ui/settings

# Both leaders and workers serve settings descriptors. Install the new topic
# descriptor on every unit; there is no legacy pin-keyed telemetry support.
if [ ! -f "$ASSET" ] || [ ! -s "$ASSET" ] || ! grep -q '  - key: channel_dc' "$ASSET"; then
    sudo -u pioreactor -i pio log -l ERROR -m "Missing or invalid PWM settings update asset: $ASSET"
    exit 1
fi

install -d -o pioreactor -g www-data -m 2775 "$SETTINGS_DIR"
TMP_DESCRIPTOR="$(mktemp "$SETTINGS_DIR/.13_pwms.yaml.XXXXXX")"
trap 'rm -f "$TMP_DESCRIPTOR"' EXIT
install -o pioreactor -g www-data -m 0664 "$ASSET" "$TMP_DESCRIPTOR"
mv "$TMP_DESCRIPTOR" "$SETTINGS_DIR/13_pwms.yaml"
cmp "$ASSET" "$SETTINGS_DIR/13_pwms.yaml"

bash "$SCRIPT_DIR/20_install_bootfs_plugins.sh"
