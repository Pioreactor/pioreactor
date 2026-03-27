#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/pioreactor.env
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
install_checked_asset "$INSTALL_PLUGIN_SRC" "$INSTALL_PLUGIN_DST" root root 0755
install_checked_asset "$UNINSTALL_PLUGIN_SRC" "$UNINSTALL_PLUGIN_DST" root root 0755
