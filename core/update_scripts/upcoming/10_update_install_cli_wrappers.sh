#!/bin/bash

set -xeu

export LC_ALL=C

ENV_FILE=/etc/pioreactor.env
PIO_WRAPPER=/usr/local/bin/pio
PIOS_WRAPPER=/usr/local/bin/pios
PIO_TARGET=/opt/pioreactor/venv/bin/pio
PIOS_TARGET=/opt/pioreactor/venv/bin/pios

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

echo "Installed:"
echo "  $PIO_WRAPPER -> wrapper for $PIO_TARGET"
echo "  $PIOS_WRAPPER -> wrapper for $PIOS_TARGET"
