#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR_DIR="/home/pioreactor/.pioreactor"
SHARED_CONFIG="$DOT_PIOREACTOR_DIR/config.ini"
UNIT_CONFIG="$DOT_PIOREACTOR_DIR/unit_config.ini"
CRUDINI="/opt/pioreactor/venv/bin/crudini"

if [ ! -f "$UNIT_CONFIG" ]; then
    exit 0
fi

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

# Pioreactor 26.4.0 wrote plugin-provided ui.* sections into unit_config.ini.
# Preserve an existing shared value as the operator's choice, then remove the stale local section.
"$CRUDINI" --get "$UNIT_CONFIG" | while IFS= read -r SECTION; do
    case "$SECTION" in
        ui.*)
            if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
                "$CRUDINI" --get "$UNIT_CONFIG" "$SECTION" | while IFS= read -r OPTION; do
                    if ! "$CRUDINI" --get "$SHARED_CONFIG" "$SECTION" "$OPTION" >/dev/null 2>&1; then
                        VALUE=$("$CRUDINI" --get "$UNIT_CONFIG" "$SECTION" "$OPTION")
                        "$CRUDINI" --set "$SHARED_CONFIG" "$SECTION" "$OPTION" "$VALUE"
                    fi
                done
            fi

            "$CRUDINI" --del "$UNIT_CONFIG" "$SECTION"
            ;;
    esac
done

chown pioreactor:www-data "$UNIT_CONFIG"
chmod g+w "$UNIT_CONFIG"

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    chown pioreactor:www-data "$SHARED_CONFIG"
    chmod g+w "$SHARED_CONFIG"
    sudo -u pioreactor -i pios sync-configs --shared || :
fi
