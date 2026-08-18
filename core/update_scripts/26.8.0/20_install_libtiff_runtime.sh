#!/bin/bash

set -xeu

export LC_ALL=C


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

package_is_installed_at_least() {
    local package_name="$1"
    local minimum_version="$2"
    local status
    local installed_version

    status=$(dpkg-query --show --showformat='${Status}' "$package_name" 2>/dev/null || :)
    [ "$status" = "install ok installed" ] || return 1

    installed_version=$(dpkg-query --show --showformat='${Version}' "$package_name")
    dpkg --compare-versions "$installed_version" ge "$minimum_version"
}

find_libtiff_path() {
    ldconfig -p | awk '$1 == "libtiff.so.6" { print $NF; exit }'
}

validate_package() {
    local package="$1"
    local expected_sha256="$2"
    local expected_package_name="$3"

    if [ ! -f "$package" ] || [ ! -s "$package" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty Debian update asset: $package"
        exit 1
    fi

    if ! printf '%s  %s\n' "$expected_sha256" "$package" | sha256sum --check --status; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset checksum: $package"
        exit 1
    fi

    if [ "$(dpkg-deb --field "$package" Package)" != "$expected_package_name" ] || \
        [ "$(dpkg-deb --field "$package" Architecture)" != "$ARCHITECTURE" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset metadata: $package"
        exit 1
    fi
}

ARCHITECTURE=$(dpkg --print-architecture)
case "$ARCHITECTURE" in
    armhf)
        PACKAGES=(
            "$SCRIPT_DIR/libjbig0_2.1-6.1_armhf.deb"
            "$SCRIPT_DIR/libjpeg62-turbo_2.1.5-2_armhf.deb"
            "$SCRIPT_DIR/liblerc4_4.0.0+ds-2_armhf.deb"
            "$SCRIPT_DIR/libtiff6_4.5.0-6+deb12u4_armhf.deb"
        )
        SHA256S=(
            "3c49626bd5eab9896fa82b4b4d4ca1627d6d70894048b3a9650d2ee4b92f53d0"
            "963d926c218d488a873fdf68a2cd17800febd91aeddfb7b731ac6db16c8c2f46"
            "a7ba911e38fb08d5a1a6487d57880abad9e59fdfe4b5701ba619a3f7c8abcab6"
            "11b4e6c214349b1ddb53828954a9dafa0e805080f04bb3e67a8c610aea444968"
        )
        ;;
    arm64)
        PACKAGES=(
            "$SCRIPT_DIR/libjbig0_2.1-6.1_arm64.deb"
            "$SCRIPT_DIR/libjpeg62-turbo_2.1.5-2_arm64.deb"
            "$SCRIPT_DIR/liblerc4_4.0.0+ds-2_arm64.deb"
            "$SCRIPT_DIR/libtiff6_4.5.0-6+deb12u4_arm64.deb"
        )
        SHA256S=(
            "098a382f51781c149e37aa25aeacfd54f26fdadfcbe5dc3ebf8713ef72efa6bd"
            "de66f186f3ff3c1d10c2e75ae056b019b3f7f091f51096a06cade48b2dea875b"
            "c5294ed128ac375249098c43be9805c787ed1c65703fe1d877ead4213904f123"
            "d88aa87e5e786f322048683cab56ae922448f501e9b402747d0a883738ce35ce"
        )
        ;;
    *)
        sudo -u pioreactor -i pio log -l ERROR -m "No bundled libtiff6 package is available for $ARCHITECTURE."
        exit 1
        ;;
esac

PACKAGE_NAMES=("libjbig0" "libjpeg62-turbo" "liblerc4" "libtiff6")
MINIMUM_VERSIONS=("2.0" "1.3.1" "3.0" "4.5.0-6+deb12u4")
PACKAGES_TO_INSTALL=()

for index in "${!PACKAGES[@]}"; do
    validate_package "${PACKAGES[$index]}" "${SHA256S[$index]}" "${PACKAGE_NAMES[$index]}"

    if ! package_is_installed_at_least "${PACKAGE_NAMES[$index]}" "${MINIMUM_VERSIONS[$index]}"; then
        PACKAGES_TO_INSTALL+=("${PACKAGES[$index]}")
    fi
done

if [ "${#PACKAGES_TO_INSTALL[@]}" -gt 0 ]; then
    # Install dependencies and libtiff6 in one transaction so dpkg can configure
    # a libtiff6 package left unpacked by the original 26.8.0 update.
    dpkg --install "${PACKAGES_TO_INSTALL[@]}"
fi

ldconfig

for index in "${!PACKAGE_NAMES[@]}"; do
    if ! package_is_installed_at_least "${PACKAGE_NAMES[$index]}" "${MINIMUM_VERSIONS[$index]}"; then
        sudo -u pioreactor -i pio log -l ERROR -m "${PACKAGE_NAMES[$index]} is not fully installed after the libtiff6 repair."
        exit 1
    fi
done

LIBTIFF_PATH=$(find_libtiff_path)
if [ -z "$LIBTIFF_PATH" ] || [ ! -e "$LIBTIFF_PATH" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "libtiff6 was installed, but libtiff.so.6 is unavailable."
    exit 1
fi
