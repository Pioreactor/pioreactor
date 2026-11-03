#!/bin/bash

set -xeu

export LC_ALL=C

# `ir_led_intensity=auto` is no longer supported: OD reading now needs a fixed IR LED intensity.
# Replace `auto` with 80, the default for new installs. The leader's config.ini is the cluster-wide
# copy, and each unit's unit_config.ini can override it, so check both on every unit.
DOT_PIOREACTOR="/home/pioreactor/.pioreactor"
CRUDINI="/opt/pioreactor/venv/bin/crudini"
SECTION="od_reading.config"
KEY="ir_led_intensity"

for CONFIG_FILE in "$DOT_PIOREACTOR/config.ini" "$DOT_PIOREACTOR/unit_config.ini"; do
    [ -f "$CONFIG_FILE" ] || continue

    value=$(sudo -u pioreactor "$CRUDINI" --get "$CONFIG_FILE" "$SECTION" "$KEY" 2>/dev/null || :)
    if [ "$(echo "$value" | tr '[:upper:]' '[:lower:]')" = "auto" ]; then
        sudo -u pioreactor "$CRUDINI" --ini-options=nospace --set "$CONFIG_FILE" "$SECTION" "$KEY" 80
        chown pioreactor:www-data "$CONFIG_FILE"
        sudo -u pioreactor -i pio log -l INFO -m "Changed [$SECTION] $KEY from auto to 80 in $CONFIG_FILE, since auto is no longer supported."
    fi
done
