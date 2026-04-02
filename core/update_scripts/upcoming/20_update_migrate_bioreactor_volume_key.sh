#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
CRUDINI=/opt/pioreactor/venv/bin/crudini

if [ ! -x "$CRUDINI" ]; then
    echo "Missing executable $CRUDINI" >&2
    exit 1
fi

migrate_bioreactor_config_key() {
    local config_path="$1"

    [ -f "$config_path" ] || return 0

    local old_value=""
    local new_value=""
    old_value=$("$CRUDINI" --get "$config_path" bioreactor max_working_volume_ml 2>/dev/null || true)
    new_value=$("$CRUDINI" --get "$config_path" bioreactor efflux_tube_volume_ml 2>/dev/null || true)

    if [ -n "$old_value" ] && [ -z "$new_value" ]; then
        "$CRUDINI" --set "$config_path" bioreactor efflux_tube_volume_ml "$old_value"
    fi

    if [ -n "$old_value" ]; then
        "$CRUDINI" --del "$config_path" bioreactor max_working_volume_ml || :
    fi
}

if [ -f "$CONFIG" ]; then
    LEADER_HOSTNAME=$("$CRUDINI" --get "$CONFIG" cluster.topology leader_hostname)
else
    LEADER_HOSTNAME=""
fi

migrate_bioreactor_config_key "$CONFIG"
migrate_bioreactor_config_key "$DOT_PIOREACTOR/unit_config.ini"

for ini_path in "$DOT_PIOREACTOR"/config_*.ini; do
    [ -e "$ini_path" ] || continue
    migrate_bioreactor_config_key "$ini_path"
done

sudo -u pioreactor -i /opt/pioreactor/venv/bin/python - <<'PY'
from pioreactor.utils import local_persistent_storage

OLD_KEY = "max_working_volume_ml"
NEW_KEY = "efflux_tube_volume_ml"

with local_persistent_storage("bioreactor") as cache:
    old_keys = [key for key in cache.iterkeys() if isinstance(key, tuple) and len(key) == 2 and key[1] == OLD_KEY]
    for experiment, _ in old_keys:
        new_key = (experiment, NEW_KEY)
        if new_key not in cache:
            cache[new_key] = cache[(experiment, OLD_KEY)]
        del cache[(experiment, OLD_KEY)]
PY

if [ -n "$LEADER_HOSTNAME" ] && [ "$LEADER_HOSTNAME" = "$(hostname)" ]; then
    sudo -u pioreactor -i pios sync-configs --shared || :
fi
