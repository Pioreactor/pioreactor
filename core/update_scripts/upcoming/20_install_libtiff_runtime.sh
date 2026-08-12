#!/bin/bash

set -xeu

export LC_ALL=C


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_libtiff_path() {
    ldconfig -p | awk '$1 == "libtiff.so.6" { print $NF; exit }'
}

ldconfig
LIBTIFF_PATH=$(find_libtiff_path)
if [ -n "$LIBTIFF_PATH" ] && [ -e "$LIBTIFF_PATH" ]; then
    exit 0
fi

ARCHITECTURE=$(dpkg --print-architecture)
case "$ARCHITECTURE" in
    armhf)
        PACKAGE="$SCRIPT_DIR/libtiff6_4.5.0-6+deb12u4_armhf.deb"
        SHA256="11b4e6c214349b1ddb53828954a9dafa0e805080f04bb3e67a8c610aea444968"
        ;;
    arm64)
        PACKAGE="$SCRIPT_DIR/libtiff6_4.5.0-6+deb12u4_arm64.deb"
        SHA256="d88aa87e5e786f322048683cab56ae922448f501e9b402747d0a883738ce35ce"
        ;;
    *)
        sudo -u pioreactor -i pio log -l ERROR -m "No bundled libtiff6 package is available for $ARCHITECTURE."
        exit 1
        ;;
esac

if [ ! -f "$PACKAGE" ] || [ ! -s "$PACKAGE" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty libtiff6 update asset: $PACKAGE"
    exit 1
fi

if ! printf '%s  %s\n' "$SHA256" "$PACKAGE" | sha256sum --check --status; then
    sudo -u pioreactor -i pio log -l ERROR -m "Invalid libtiff6 update asset checksum: $PACKAGE"
    exit 1
fi

if [ "$(dpkg-deb --field "$PACKAGE" Package)" != "libtiff6" ] || \
    [ "$(dpkg-deb --field "$PACKAGE" Architecture)" != "$ARCHITECTURE" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Invalid libtiff6 update asset metadata: $PACKAGE"
    exit 1
fi

dpkg --install "$PACKAGE"
ldconfig

LIBTIFF_PATH=$(find_libtiff_path)
if [ -z "$LIBTIFF_PATH" ] || [ ! -e "$LIBTIFF_PATH" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "libtiff6 was installed, but libtiff.so.6 is unavailable."
    exit 1
fi
