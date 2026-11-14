#!/bin/bash

set -xeu

export LC_ALL=C

# mosquitto is now installed and configured on every unit, but only leaders run the broker.
# Workers may be offline during updates, so the trixie packages are bundled here. Bookworm (deb12)
# packages don't work: they depend on libssl3, which 32-bit (armhf) trixie doesn't provide.
# This runs from pre_update.sh, so a failure leaves the unit on its previous version.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Leaders already run the broker from their image; never touch their packages or config.
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
if [ "$(hostname)" = "$LEADER_HOSTNAME" ]; then
    exit 0
fi

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

# Workers that already have mosquitto (from their image, or installed by hand) skip the install,
# but still get the broker config and a disabled broker below.
if ! { package_is_installed_at_least mosquitto "2.0" && package_is_installed_at_least mosquitto-clients "2.0"; }; then
    ARCHITECTURE=$(dpkg --print-architecture)
    PACKAGE_NAMES=("libcjson1" "libdlt2" "libwebsockets19t64" "libwrap0" "libmosquitto1" "mosquitto" "mosquitto-clients")
    case "$ARCHITECTURE" in
        armhf)
            # from raspbian.raspberrypi.com trixie
            MINIMUM_VERSIONS=("1.7.18-3.1+deb13u1" "2.18.10-10+b1" "4.3.5-1+deb13u3" "7.6.q-36" "2.0.21-1" "2.0.21-1" "2.0.21-1")
            PACKAGES=(
                "$SCRIPT_DIR/libcjson1_1.7.18-3.1+deb13u1_armhf.deb"
                "$SCRIPT_DIR/libdlt2_2.18.10-10+b1_armhf.deb"
                "$SCRIPT_DIR/libwebsockets19t64_4.3.5-1+deb13u3_armhf.deb"
                "$SCRIPT_DIR/libwrap0_7.6.q-36_armhf.deb"
                "$SCRIPT_DIR/libmosquitto1_2.0.21-1_armhf.deb"
                "$SCRIPT_DIR/mosquitto_2.0.21-1_armhf.deb"
                "$SCRIPT_DIR/mosquitto-clients_2.0.21-1_armhf.deb"
            )
            SHA256S=(
                "61103317f6149697ca68124fc880f7f5a5955d5c3a3ae22b8d7a3d2f69008f3d"
                "656ab76c933d0b25b8aad2c442f8ab6cecf342bc87a1ac663e67d218de4830d4"
                "c59aed05846263a2ad0ba11aa3b9c12789858bba02bc42d3052869784e55d8fa"
                "34d4fae7e4efca2092d8f04cdc1282974fb6fd1b0e1f330c69d436727ac440ee"
                "b148ef4b5e5ecef1ed8a5bd05f584455410ef2af6efdb217b9b4910edef664f2"
                "94e6c3ae771d42d1c67e5133af3101ef4732c7faf34976e006c72b124d5f074f"
                "72ac94cc821181ca80df619a362f41086ffdd73d28cc9cdb12d797863673922e"
            )
            ;;
        arm64)
            # from deb.debian.org trixie
            MINIMUM_VERSIONS=("1.7.18-3.1+deb13u1" "2.18.10-10+b1" "4.3.5-1+deb13u2" "7.6.q-36" "2.0.21-1" "2.0.21-1" "2.0.21-1")
            PACKAGES=(
                "$SCRIPT_DIR/libcjson1_1.7.18-3.1+deb13u1_arm64.deb"
                "$SCRIPT_DIR/libdlt2_2.18.10-10+b1_arm64.deb"
                "$SCRIPT_DIR/libwebsockets19t64_4.3.5-1+deb13u2_arm64.deb"
                "$SCRIPT_DIR/libwrap0_7.6.q-36_arm64.deb"
                "$SCRIPT_DIR/libmosquitto1_2.0.21-1_arm64.deb"
                "$SCRIPT_DIR/mosquitto_2.0.21-1_arm64.deb"
                "$SCRIPT_DIR/mosquitto-clients_2.0.21-1_arm64.deb"
            )
            SHA256S=(
                "f8a6ce78b0d4b1db40b16e0330fb1dfcd54a15c4a1f6798afd631e99f30fe707"
                "e3c98fb15eb7e7aaadc19d580121afce6bf1c802b0ac71c854e27447983c2658"
                "7c8d5852bb81b4ebddf1893ba8a92c22613364227ea9de15ac899178cbc1975d"
                "fd2e54582a07fba9c8a6f78c68dcc6d3c8cf1c70632a68124394bde4dccf52ea"
                "1f768c324c8c1198b79d83a00115bcba7afab9e6d335a6029026ed896b601b61"
                "08e7c2488bb502cac9503662191fdd66a57eadfc7b5150732b86585b4074f856"
                "357b563845683e4ba9cc56d679c730f18e8c02df28cd5f5c97776b6bf9230e4e"
            )
            ;;
        *)
            sudo -u pioreactor -i pio log -l ERROR -m "No bundled mosquitto package is available for $ARCHITECTURE."
            exit 1
            ;;
    esac

    # Units where 26.11.0's bookworm packages failed have them unpacked but not configured. Those
    # don't count as installed here, so the trixie packages replace and configure them.
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
fi

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

# dpkg enables and starts mosquitto.service on install. Workers don't run a broker.
systemctl disable --now mosquitto.service
