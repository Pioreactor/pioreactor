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
test -x /opt/pioreactor/venv/bin/pip
command -v unzip
command -v timeout
systemctl cat pioreactor.target >/dev/null
systemctl cat firstboot.service everyboot.service >/dev/null

# Validate every sidecar before changing any installed files.
for asset in bootfs_plugins.sh bootfs_plugins.service bootfs_plugins.conf; do
    if [ ! -f "$SCRIPT_DIR/$asset" ] || [ ! -s "$SCRIPT_DIR/$asset" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty bootfs plugin update asset: $asset"
        exit 1
    fi
done

install_checked_asset() {
    local src="$1" dst="$2" mode="$3" tmp
    install -d -o root -g root -m 0755 "$(dirname "$dst")"
    tmp="$(mktemp "$(dirname "$dst")/.bootfs_plugins.XXXXXX")"
    install -o root -g root -m "$mode" "$src" "$tmp"
    mv "$tmp" "$dst"
    cmp "$src" "$dst"
}

# Retire the early config watcher: config arrival must not trigger installation
# during worker onboarding, before its reboot.
if systemctl cat bootfs_plugins.path >/dev/null 2>&1; then
    systemctl disable --now bootfs_plugins.path
    rm -f /etc/systemd/system/bootfs_plugins.path
fi
if [ -f /etc/systemd/system/pioreactor.target ]; then
    sed -i 's/ bootfs_plugins.path//g' /etc/systemd/system/pioreactor.target
fi

install_checked_asset "$SCRIPT_DIR/bootfs_plugins.sh" /usr/local/bin/bootfs_plugins.sh 0755
install_checked_asset "$SCRIPT_DIR/bootfs_plugins.service" /etc/systemd/system/bootfs_plugins.service 0644
install_checked_asset "$SCRIPT_DIR/bootfs_plugins.conf" /etc/systemd/system/pioreactor.target.d/bootfs_plugins.conf 0644

systemctl daemon-reload
systemctl cat bootfs_plugins.service >/dev/null
# The existing target pulls in the service on the next boot. Do not start plugin
# installation inside the app update, or restart the web/Huey services here.
