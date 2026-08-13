#!/bin/bash

set -eu

export LC_ALL=C

readonly TAG="pioreactor-wifi-recovery"
readonly FAILED_ATTEMPT_STAMP="/run/pioreactor/wifi-recovery-failed"

log() {
    /usr/bin/logger -t "$TAG" -- "$1"
}

# This recovery is intentionally limited to an SDIO-backed wlan0. Deriving the
# MMC host from wlan0 makes it impossible to accidentally reset the SD card.
if [ ! -e /sys/class/net/wlan0/device ]; then
    exit 0
fi

wifi_device="$(readlink -f /sys/class/net/wlan0/device)"
mmc_host="$(printf '%s\n' "$wifi_device" | /usr/bin/sed -n 's#.*\/mmc_host\/\(mmc[0-9][0-9]*\)\/.*#\1#p')"

if [ -z "$mmc_host" ]; then
    exit 0
fi

# A gateway failure alone is not enough: local-only or ICMP-filtering networks
# are valid. Require a fresh, high-confidence brcmfmac/SDIO failure as well.
failure_pattern="${mmc_host}: Timeout waiting for hardware interrupt"
failure_pattern="${failure_pattern}|CMD53.*failed -110"
failure_pattern="${failure_pattern}|brcmf_proto_bcdc_msg failed w/status -110"
failure_pattern="${failure_pattern}|BRCMF_C_GET_ASSOCLIST failed, err=-110"
failure_pattern="${failure_pattern}|brcmf_sdio_(txfail|rxfail)"
failure_pattern="${failure_pattern}|brcmf_sdio_hdparse: HW header checksum error"

if ! /usr/bin/journalctl -k -b --since "2 minutes ago" --no-pager -o cat \
    | /usr/bin/grep -Eq "$failure_pattern"; then
    exit 0
fi

gateway="$(/usr/sbin/ip -4 route show default dev wlan0 | /usr/bin/awk '$1 == "default" && $2 == "via" {print $3; exit}')"

if [ -z "$gateway" ] || /usr/bin/ping -I wlan0 -c 3 -W 1 "$gateway" >/dev/null 2>&1; then
    exit 0
fi

if [ -e "$FAILED_ATTEMPT_STAMP" ]; then
    exit 0
fi

/usr/bin/mkdir -p "$(dirname "$FAILED_ATTEMPT_STAMP")"
/usr/bin/touch "$FAILED_ATTEMPT_STAMP"

host_device="$(readlink -f "/sys/class/mmc_host/$mmc_host/device")"
host_driver="$(readlink -f "$host_device/driver")"
host_name="$(basename "$host_device")"

if [ ! -w "$host_driver/unbind" ] || [ ! -w "$host_driver/bind" ]; then
    log "Detected a Wi-Fi SDIO failure, but the $mmc_host host cannot be reset."
    exit 1
fi

log "Detected a Wi-Fi SDIO failure through $mmc_host; resetting $host_name."

printf '%s\n' "$host_name" > "$host_driver/unbind"
/usr/bin/sleep 2
printf '%s\n' "$host_name" > "$host_driver/bind"

for _ in $(/usr/bin/seq 1 30); do
    if [ -e /sys/class/net/wlan0 ]; then
        break
    fi
    /usr/bin/sleep 1
done

if [ ! -e /sys/class/net/wlan0 ]; then
    log "Wi-Fi SDIO reset failed: wlan0 did not return."
    exit 1
fi

if ! /usr/bin/timeout 60s /usr/bin/nmcli device connect wlan0 >/dev/null 2>&1; then
    log "Wi-Fi SDIO reset reprobed wlan0, but NetworkManager could not reconnect it."
    exit 1
fi

# Reprobing brcmfmac restores its default of power saving enabled.
/sbin/iw dev wlan0 set power_save off || log "Wi-Fi recovered, but power saving could not be disabled."

if /usr/bin/ping -I wlan0 -c 3 -W 1 "$gateway" >/dev/null 2>&1; then
    /usr/bin/rm -f "$FAILED_ATTEMPT_STAMP"
    log "Wi-Fi SDIO recovery succeeded; wlan0 can reach $gateway."
    exit 0
fi

log "Wi-Fi SDIO reset completed, but wlan0 still cannot reach $gateway."
exit 1
