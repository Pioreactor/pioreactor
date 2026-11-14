#!/bin/bash

set -xeu

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

# Images ship ca-certificates 20250419, which still trusts the roots behind the compromised eMudhra
# intermediates (https://emudhra.we-have-a-problem.com/, Debian bug #1151413). 20250419+deb13u1
# distrusts "emSign ECC Root CA - G3" and "Comodo AAA Services root". Units may be offline during
# updates, so the trixie-security package is bundled here. It is Architecture: all.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PACKAGE_NAME="ca-certificates"
MINIMUM_VERSION="20250419+deb13u1"
# from deb.debian.org/debian-security trixie-security
PACKAGE="$SCRIPT_DIR/ca-certificates_20250419+deb13u1_all.deb"
EXPECTED_SHA256="c10585ac22c7f617a73d394eea29ba71d0356f350ae973b19043d1b017f80f54"
DISTRUSTED_CERTS=(
    "/etc/ssl/certs/emSign_ECC_Root_CA_-_G3.pem"
    "/etc/ssl/certs/Comodo_AAA_Services_root.pem"
)

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

validate_package() {
    if [ ! -f "$PACKAGE" ] || [ ! -s "$PACKAGE" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty Debian update asset: $PACKAGE"
        exit 1
    fi

    if ! printf '%s  %s\n' "$EXPECTED_SHA256" "$PACKAGE" | sha256sum --check --status; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset checksum: $PACKAGE"
        exit 1
    fi

    if [ "$(dpkg-deb --field "$PACKAGE" Package)" != "$PACKAGE_NAME" ] || \
        [ "$(dpkg-deb --field "$PACKAGE" Architecture)" != "all" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset metadata: $PACKAGE"
        exit 1
    fi
}

if ! package_is_installed_at_least "$PACKAGE_NAME" "$MINIMUM_VERSION"; then
    validate_package
    dpkg --install "$PACKAGE"
fi

if ! package_is_installed_at_least "$PACKAGE_NAME" "$MINIMUM_VERSION"; then
    sudo -u pioreactor -i pio log -l ERROR -m "$PACKAGE_NAME is not fully installed after the ca-certificates update."
    exit 1
fi

for cert in "${DISTRUSTED_CERTS[@]}"; do
    if [ -e "$cert" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "$cert is still trusted after the ca-certificates update."
        exit 1
    fi
done
