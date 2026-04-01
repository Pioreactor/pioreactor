#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/pioreactor.env
DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
CRUDINI=/opt/pioreactor/venv/bin/crudini
PIO_WRAPPER=/usr/local/bin/pio
PIOS_WRAPPER=/usr/local/bin/pios
PIO_TARGET=/opt/pioreactor/venv/bin/pio
PIOS_TARGET=/opt/pioreactor/venv/bin/pios
INSTALL_PLUGIN_SRC="$SCRIPT_DIR/install_pioreactor_plugin.sh"
UNINSTALL_PLUGIN_SRC="$SCRIPT_DIR/uninstall_pioreactor_plugin.sh"
INSTALL_PLUGIN_DST="/usr/local/bin/install_pioreactor_plugin.sh"
UNINSTALL_PLUGIN_DST="/usr/local/bin/uninstall_pioreactor_plugin.sh"

if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE" >&2
    exit 1
fi

if [ ! -x "$CRUDINI" ]; then
    echo "Missing executable $CRUDINI" >&2
    exit 1
fi

if [ ! -x "$PIO_TARGET" ]; then
    echo "Missing executable $PIO_TARGET" >&2
    exit 1
fi

if [ ! -x "$PIOS_TARGET" ]; then
    echo "Missing executable $PIOS_TARGET" >&2
    exit 1
fi

require_nonempty_asset() {
    local path="$1"
    [ -f "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Missing update asset: $path"
        exit 1
    }
    [ -s "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Empty update asset: $path"
        exit 1
    }
}

install_checked_asset() {
    local src="$1"
    local dst="$2"
    local owner="$3"
    local group="$4"
    local mode="$5"

    require_nonempty_asset "$src"

    local tmp
    tmp="$(mktemp)"
    install -o "$owner" -g "$group" -m "$mode" "$src" "$tmp"
    install -d -o "$owner" -g "$group" -m 0755 "$(dirname "$dst")"
    mv "$tmp" "$dst"

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
    [ -x "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is not executable"
        exit 1
    }
}

install_wrapper() {
    local wrapper_path="$1"
    local target_path="$2"
    local tmp_file

    tmp_file="$(mktemp)"
    cat >"$tmp_file" <<EOF
#!/bin/sh
set -a
. /etc/pioreactor.env
set +a
exec $target_path "\$@"
EOF

    install -o root -g root -m 0755 "$tmp_file" "$wrapper_path"
    rm -f "$tmp_file"
}

install_wrapper "$PIO_WRAPPER" "$PIO_TARGET"
install_wrapper "$PIOS_WRAPPER" "$PIOS_TARGET"

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

echo "Installed:"
echo "  $PIO_WRAPPER -> wrapper for $PIO_TARGET"
echo "  $PIOS_WRAPPER -> wrapper for $PIOS_TARGET"


install_checked_asset "$INSTALL_PLUGIN_SRC" "$INSTALL_PLUGIN_DST" root root 0755
install_checked_asset "$UNINSTALL_PLUGIN_SRC" "$UNINSTALL_PLUGIN_DST" root root 0755
