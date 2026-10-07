#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Boot partition inputs and firstboot/everyboot are Raspberry Pi image features.
# Generic Linux leaders do not have this boot lifecycle.
if [ ! -f /proc/device-tree/model ] || ! grep -q 'Raspberry Pi' /proc/device-tree/model; then
    exit 0
fi

test -d /boot/firmware
test -s /etc/pioreactor.env
test -x /opt/pioreactor/venv/bin/python
command -v timeout
systemctl cat pioreactor.target >/dev/null
systemctl cat firstboot.service everyboot.service >/dev/null

# Validate every sidecar before changing any installed files.
for asset in bootfs_files.sh bootfs_files.service bootfs_files.conf; do
    if [ ! -f "$SCRIPT_DIR/$asset" ] || [ ! -s "$SCRIPT_DIR/$asset" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty bootfs file update asset: $asset"
        exit 1
    fi
done

install_checked_asset() {
    local src="$1" dst="$2" mode="$3" tmp
    install -d -o root -g root -m 0755 "$(dirname "$dst")"
    tmp="$(mktemp "$(dirname "$dst")/.bootfs_files.XXXXXX")"
    install -o root -g root -m "$mode" "$src" "$tmp"
    mv "$tmp" "$dst"
    cmp "$src" "$dst"
}

install_checked_asset "$SCRIPT_DIR/bootfs_files.sh" /usr/local/bin/bootfs_files.sh 0755
install_checked_asset "$SCRIPT_DIR/bootfs_files.service" /etc/systemd/system/bootfs_files.service 0644
install_checked_asset "$SCRIPT_DIR/bootfs_files.conf" /etc/systemd/system/pioreactor.target.d/bootfs_files.conf 0644

systemctl daemon-reload
systemctl cat bootfs_files.service >/dev/null
# Import staged files on the next boot, after the updated wheel is installed.
