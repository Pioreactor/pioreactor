#!/bin/bash

set -xeu

export LC_ALL=C

# mosquitto is now installed and configured on every unit, but only leaders run the broker.
# Workers may be offline during updates, so the bookworm packages are bundled here.

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

validate_package() {
    local package="$1"
    local expected_sha256="$2"
    local expected_package_name="$3"
    local package_architecture

    if [ ! -f "$package" ] || [ ! -s "$package" ]; then
        sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty Debian update asset: $package"
        exit 1
    fi

    if ! printf '%s  %s\n' "$expected_sha256" "$package" | sha256sum --check --status; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset checksum: $package"
        exit 1
    fi

    package_architecture=$(dpkg-deb --field "$package" Architecture)
    if [ "$(dpkg-deb --field "$package" Package)" != "$expected_package_name" ] || \
        { [ "$package_architecture" != "$ARCHITECTURE" ] && [ "$package_architecture" != "all" ]; }; then
        sudo -u pioreactor -i pio log -l ERROR -m "Invalid Debian update asset metadata: $package"
        exit 1
    fi
}

if package_is_installed_at_least mosquitto "2.0" && package_is_installed_at_least mosquitto-clients "2.0"; then
    # leaders, and any unit already updated.
    exit 0
fi

ARCHITECTURE=$(dpkg --print-architecture)
case "$ARCHITECTURE" in
    armhf)
        # from raspbian.raspberrypi.com bookworm
        PACKAGE_NAMES=("libcjson1" "libdlt2" "libmosquitto1" "mosquitto" "mosquitto-clients")
        MINIMUM_VERSIONS=("1.7.13" "2.18.8" "2.0.11-1.2+deb12u2" "2.0.11-1.2+deb12u2" "2.0.11-1.2+deb12u2")
        PACKAGES=(
            "$SCRIPT_DIR/libcjson1_1.7.15-1+deb12u4_armhf.deb"
            "$SCRIPT_DIR/libdlt2_2.18.8-6_armhf.deb"
            "$SCRIPT_DIR/libmosquitto1_2.0.11-1.2+deb12u2_armhf.deb"
            "$SCRIPT_DIR/mosquitto_2.0.11-1.2+deb12u2_armhf.deb"
            "$SCRIPT_DIR/mosquitto-clients_2.0.11-1.2+deb12u2_armhf.deb"
        )
        SHA256S=(
            "a609526d122a6b5b9d98f58d3836239a75cccde09e8eb5fcddd511f542873c82"
            "a66fa29f9cb1bc39a5208ec3fee54799be93b97ef0a02de06e6299cdb933248b"
            "a4b8ed7bf0186fcfdc1836b905256501f3b9bde13b4fda74b7a0deb51702f460"
            "b35f44a0c7ff5b358be7b640310b5ebd440d9facdfc19eb7ab67cf3d0c2e1517"
            "70f426876fb703eaa40e42796e500ac2ee615d709158c56f3592b4974f510d97"
        )
        ;;
    arm64)
        # from deb.debian.org bookworm
        PACKAGE_NAMES=("libcjson1" "libdlt2" "libmosquitto1" "lsb-base" "mosquitto" "mosquitto-clients")
        MINIMUM_VERSIONS=("1.7.13" "2.18.8" "2.0.11-1.2+deb12u2" "4.1+Debian3" "2.0.11-1.2+deb12u2" "2.0.11-1.2+deb12u2")
        PACKAGES=(
            "$SCRIPT_DIR/libcjson1_1.7.15-1+deb12u4_arm64.deb"
            "$SCRIPT_DIR/libdlt2_2.18.8-6_arm64.deb"
            "$SCRIPT_DIR/libmosquitto1_2.0.11-1.2+deb12u2_arm64.deb"
            "$SCRIPT_DIR/lsb-base_11.6_all.deb"
            "$SCRIPT_DIR/mosquitto_2.0.11-1.2+deb12u2_arm64.deb"
            "$SCRIPT_DIR/mosquitto-clients_2.0.11-1.2+deb12u2_arm64.deb"
        )
        SHA256S=(
            "67b9f4d780a401b28bcce3d23a0a26efbdf040d7a012f1d73f8142a641925e2e"
            "9e5d3fff3b7c9a43265ec76d2e5c9d663426daf4d000026835142a6aa7309436"
            "05e3aeb5dcffba2f820c1ec46458a1dc0f8349617d2374897736b414806ffff9"
            "f8bedd167280e76636df3a1bc023cd2906d458916c1af4c1d7912c5b971fc642"
            "f94ae2b88b7ca3aae474f86ac3397abc467c56ee638942b88db46cd89895991b"
            "88ec20b5375b835a62f609a24186c9fe1782c673319f2f4e1e880dcaba4bc2d8"
        )
        ;;
    *)
        sudo -u pioreactor -i pio log -l ERROR -m "No bundled mosquitto package is available for $ARCHITECTURE."
        exit 1
        ;;
esac

PACKAGES_TO_INSTALL=()
for index in "${!PACKAGES[@]}"; do
    validate_package "${PACKAGES[$index]}" "${SHA256S[$index]}" "${PACKAGE_NAMES[$index]}"

    if ! package_is_installed_at_least "${PACKAGE_NAMES[$index]}" "${MINIMUM_VERSIONS[$index]}"; then
        PACKAGES_TO_INSTALL+=("${PACKAGES[$index]}")
    fi
done

dpkg --install "${PACKAGES_TO_INSTALL[@]}"

for index in "${!PACKAGE_NAMES[@]}"; do
    if ! package_is_installed_at_least "${PACKAGE_NAMES[$index]}" "${MINIMUM_VERSIONS[$index]}"; then
        sudo -u pioreactor -i pio log -l ERROR -m "${PACKAGE_NAMES[$index]} is not fully installed after the mosquitto install."
        exit 1
    fi
done

# same broker config as the leader images, so a worker can be promoted by enabling the service.
echo "pioreactor:raspberry" > /etc/mosquitto/pw.txt
mosquitto_passwd -U /etc/mosquitto/pw.txt
chown mosquitto:mosquitto /etc/mosquitto/pw.txt
chmod 0700 /etc/mosquitto/pw.txt

for LINE in \
    'log_type error' \
    'log_type warning' \
    'persistence false' \
    'listener 1883' \
    'protocol mqtt' \
    'listener 9001' \
    'protocol websockets' \
    'allow_anonymous false' \
    'max_inflight_messages 1000' \
    'password_file /etc/mosquitto/pw.txt'; do
    grep -qxF "$LINE" /etc/mosquitto/mosquitto.conf || echo "$LINE" >> /etc/mosquitto/mosquitto.conf
done

# dpkg enables and starts mosquitto.service on install. Leaders never reach here (they already
# have mosquitto), but guard anyway so a misread topology can't stop the cluster's broker.
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
if [ "$(hostname)" != "$LEADER_HOSTNAME" ]; then
    systemctl disable --now mosquitto.service
fi
