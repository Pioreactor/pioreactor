#!/bin/bash

set -xeu

export LC_ALL=C

# [stirring.config] target_rpm_outside_od_reading is removed: stirring now always uses its target RPM between OD readings.
# Where dodging is enabled, the old value was the RPM actually used, so carry it over to initial_target_rpm. Then remove the key.
# Check the shared config.ini and unit_config.ini on every unit, plus the leader's per-unit config_<unit>.ini copies,
# so a later config sync doesn't bring back the old values.
DOT_PIOREACTOR="/home/pioreactor/.pioreactor"
CRUDINI="/opt/pioreactor/venv/bin/crudini"
SECTION="stirring.config"
OLD_KEY="target_rpm_outside_od_reading"
NEW_KEY="initial_target_rpm"

is_true() {
    case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
        1 | yes | true | on) return 0 ;;
        *) return 1 ;;
    esac
}

shared_dodging=$(sudo -u pioreactor "$CRUDINI" --get "$DOT_PIOREACTOR/config.ini" "$SECTION" enable_dodging_od 2>/dev/null || :)

for CONFIG_FILE in "$DOT_PIOREACTOR/config.ini" "$DOT_PIOREACTOR/unit_config.ini" "$DOT_PIOREACTOR"/config_*.ini; do
    [ -f "$CONFIG_FILE" ] || continue

    value=$(sudo -u pioreactor "$CRUDINI" --get "$CONFIG_FILE" "$SECTION" "$OLD_KEY" 2>/dev/null || :)
    [ -n "$value" ] || continue

    dodging=$(sudo -u pioreactor "$CRUDINI" --get "$CONFIG_FILE" "$SECTION" enable_dodging_od 2>/dev/null || :)
    [ -n "$dodging" ] || dodging="$shared_dodging"

    if is_true "$dodging"; then
        sudo -u pioreactor "$CRUDINI" --ini-options=nospace --set "$CONFIG_FILE" "$SECTION" "$NEW_KEY" "$value"
        sudo -u pioreactor -i pio log -l INFO -m "Moved [$SECTION] $OLD_KEY=$value to $NEW_KEY in $CONFIG_FILE."
    fi

    sudo -u pioreactor "$CRUDINI" --del "$CONFIG_FILE" "$SECTION" "$OLD_KEY"
    chown pioreactor:www-data "$CONFIG_FILE"
done
