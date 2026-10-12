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

# Bioreactor topics now carry {"timestamp", "value"} payloads, so the leader's live
# volume and alt-media charts need to read the `value` key.
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
if [ "$(hostname)" = "$LEADER_HOSTNAME" ]; then
    CHARTS_DIR=/home/pioreactor/.pioreactor/ui/charts
    install -d -o pioreactor -g www-data -m 2775 "$CHARTS_DIR"
    for CHART in 03_alt_media_fraction.yaml 08_current_volume_ml.yaml; do
        CHART_ASSET="$SCRIPT_DIR/ui_charts_$CHART"
        if [ ! -s "$CHART_ASSET" ] || ! grep -q '^payload_key: value$' "$CHART_ASSET"; then
            sudo -u pioreactor -i pio log -l ERROR -m "Missing or invalid chart update asset: $CHART_ASSET"
            exit 1
        fi
        TMP_CHART="$(mktemp "$CHARTS_DIR/.$CHART.XXXXXX")"
        install -o pioreactor -g www-data -m 0664 "$CHART_ASSET" "$TMP_CHART"
        mv "$TMP_CHART" "$CHARTS_DIR/$CHART"
        cmp "$CHART_ASSET" "$CHARTS_DIR/$CHART"
    done
fi

bash "$SCRIPT_DIR/20_install_bootfs_plugins.sh"

bash "$SCRIPT_DIR/30_install_bootfs_files.sh"

# Onboarding saves the unit model over SSH before requesting its reboot.
WORKER_SETUP="$SCRIPT_DIR/add_new_pioreactor_worker_from_leader.sh"
test -s "$WORKER_SETUP"
TMP_WORKER_SETUP="$(mktemp /usr/local/bin/.worker-setup.XXXXXX)"
install -o root -g root -m 0755 "$WORKER_SETUP" "$TMP_WORKER_SETUP"
mv "$TMP_WORKER_SETUP" /usr/local/bin/add_new_pioreactor_worker_from_leader.sh
