#!/bin/bash

set -xeu

export LC_ALL=C

# Preserve this unit's effective between-reading RPM before removing the old setting.
# Keep the shared initial RPM unchanged: other units may have dodging disabled.
# Cluster updates do not sync config.ini between unit migrations.
DOT_PIOREACTOR="/home/pioreactor/.pioreactor"
CRUDINI="/opt/pioreactor/venv/bin/crudini"
SECTION="stirring.config"
OLD_KEY="target_rpm_outside_od_reading"
NEW_KEY="initial_target_rpm"
UNIT_CONFIG="$DOT_PIOREACTOR/unit_config.ini"

is_true() {
    case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
        1 | yes | true | on) return 0 ;;
        *) return 1 ;;
    esac
}

# Missing keys are normal on retries and on units that never configured dodging.
value=$(sudo -u pioreactor -i pio config get "$SECTION" "$OLD_KEY" 2>/dev/null || :)
dodging=$(sudo -u pioreactor -i pio config get "$SECTION" enable_dodging_od 2>/dev/null || :)
if [ -n "$value" ] && is_true "$dodging"; then
    sudo -u pioreactor "$CRUDINI" --ini-options=nospace --set "$UNIT_CONFIG" "$SECTION" "$NEW_KEY" "$value"
    chown pioreactor:www-data "$UNIT_CONFIG"
    sudo -u pioreactor -i pio log -l INFO -m "Preserved [$SECTION] $OLD_KEY=$value as $NEW_KEY in $UNIT_CONFIG."
fi

# Delete shared first, local last. After an interruption, any remaining old value
# still represents this unit's effective RPM, rather than a shadowed shared value.
for CONFIG_FILE in "$DOT_PIOREACTOR/config.ini" "$UNIT_CONFIG"; do
    [ -f "$CONFIG_FILE" ] || continue
    if sudo -u pioreactor "$CRUDINI" --get "$CONFIG_FILE" "$SECTION" "$OLD_KEY" >/dev/null 2>&1; then
        sudo -u pioreactor "$CRUDINI" --del "$CONFIG_FILE" "$SECTION" "$OLD_KEY"
        chown pioreactor:www-data "$CONFIG_FILE"
    fi
done
