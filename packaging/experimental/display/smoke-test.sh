#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
unit=pioreactor-display-smoke-$(date +%s)
systemd-run --unit="$unit" --wait --collect \
    -p User=pioreactor-display -p Group=pioreactor-display \
    -p 'SupplementaryGroups=video render input' \
    -p RootDirectory=/opt/pioreactor-display/rootfs \
    -p MountAPIVFS=yes -p BindPaths=/dev/dri \
    -p "BindReadOnlyPaths=-/run/avahi-daemon /etc/resolv.conf" \
    -p RuntimeDirectory="$unit" -p RuntimeDirectoryMode=0700 \
    -p NoNewPrivileges=yes -p RuntimeMaxSec=75 \
    --setenv=WPE_PLATFORM=headless \
    --setenv=HOME="/run/$unit" \
    --setenv=XDG_RUNTIME_DIR="/run/$unit" \
    /usr/bin/dbus-run-session -- /usr/local/bin/pioreactor-display --smoke-test "${1:-http://localhost/static/display.html}" \
    || { journalctl -u "$unit" --no-pager -n 60; exit 1; }
journalctl -u "$unit" --no-pager -n 60
