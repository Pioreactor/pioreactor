#!/bin/bash

set -xeu

export LC_ALL=C

# [od_reading.config] samples_per_second is replaced by its inverse, seconds_between_readings.
# The leader's config.ini is the cluster-wide copy, and each unit's unit_config.ini can override it,
# so check both on every unit. Rewrite the line in place to keep its position, and refresh the old comment.
DOT_PIOREACTOR="/home/pioreactor/.pioreactor"
CRUDINI="/opt/pioreactor/venv/bin/crudini"
SECTION="od_reading.config"
OLD_KEY="samples_per_second"
NEW_KEY="seconds_between_readings"

for CONFIG_FILE in "$DOT_PIOREACTOR/config.ini" "$DOT_PIOREACTOR/unit_config.ini"; do
    [ -f "$CONFIG_FILE" ] || continue

    value=$(sudo -u pioreactor "$CRUDINI" --get "$CONFIG_FILE" "$SECTION" "$OLD_KEY" 2>/dev/null || :)
    [ -n "$value" ] || continue

    seconds=$(awk -v v="$value" 'BEGIN { if (v + 0 > 0) printf "%g", 1 / v }')
    if [ -z "$seconds" ]; then
        sudo -u pioreactor -i pio log -l WARNING -m "Could not convert [$SECTION] $OLD_KEY=$value in $CONFIG_FILE. Set $NEW_KEY manually."
        continue
    fi

    sudo -u pioreactor sed -i \
        -e "s/^[[:space:]]*$OLD_KEY[[:space:]]*=.*$/$NEW_KEY=$seconds/" \
        -e "s/^# how many optical density measurements should be published per second?.*$/# seconds between optical density readings. Ex: 5 is every 5 seconds, 1800 is every 30 minutes. Recommended minimum is 1./" \
        "$CONFIG_FILE"
    chown pioreactor:www-data "$CONFIG_FILE"
    sudo -u pioreactor -i pio log -l INFO -m "Replaced [$SECTION] $OLD_KEY=$value with $NEW_KEY=$seconds in $CONFIG_FILE."
done
