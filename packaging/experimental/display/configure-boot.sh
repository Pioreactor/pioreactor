#!/bin/sh
# Image-owned templates preserve the original headless configuration.
set -eu
boot=/boot/firmware
config=/etc/pioreactor-display
rm -f /run/pioreactor-display-ready
mode=headless
[ ! -f "$boot/experimental_display" ] || mode=display
if ! cmp -s "$config/$mode.txt" "$boot/pioreactor-display.txt"; then
    install -m644 "$config/$mode.txt" "$boot/pioreactor-display.txt.new"
    mv "$boot/pioreactor-display.txt.new" "$boot/pioreactor-display.txt"
    echo "Experimental display: $mode HDMI configuration staged. Reboot to apply." | tee "$boot/experimental_display.log"
    exit 0
fi
rm -f "$boot/experimental_display.log"
if [ "$mode" = display ]; then
    touch /run/pioreactor-display-ready
    # Only displace the console when the display was actually requested.
    systemctl stop getty@tty1.service
fi
