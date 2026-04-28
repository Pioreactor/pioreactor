#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_nonempty_asset() {
    local path="$1"
    [ -f "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Missing update asset: $path"
        exit 1
    }
    [ -s "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Empty update asset: $path"
        exit 1
    }
}

install_checked_asset() {
    local src="$1"
    local dst="$2"

    require_nonempty_asset "$src"

    local tmp
    tmp="$(mktemp)"
    install -o pioreactor -g www-data -m 0644 "$src" "$tmp"
    install -d -o pioreactor -g www-data -m 0755 "$(dirname "$dst")"
    mv "$tmp" "$dst"

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
}

# TODO: the problem with this is that the numbering scheme, xx_<name>.yaml was added later, so not all machines look like this
install_checked_asset \
    "$SCRIPT_DIR/automation_dosing_01_chemostat.yaml" \
    "$DOT_PIOREACTOR/ui/automations/dosing/01_chemostat.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_dosing_02_turbidostat.yaml" \
    "$DOT_PIOREACTOR/ui/automations/dosing/02_turbidostat.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_dosing_10_fed_batch.yaml" \
    "$DOT_PIOREACTOR/ui/automations/dosing/10_fed_batch.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_dosing_11_pid_morbidostat.yaml" \
    "$DOT_PIOREACTOR/ui/automations/dosing/11_pid_morbidostat.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_dosing_99_silent.yaml" \
    "$DOT_PIOREACTOR/ui/automations/dosing/99_silent.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_led_01_light_dark_cycle.yaml" \
    "$DOT_PIOREACTOR/ui/automations/led/01_light_dark_cycle.yaml"
install_checked_asset \
    "$SCRIPT_DIR/automation_led_99_silent.yaml" \
    "$DOT_PIOREACTOR/ui/automations/led/99_silent.yaml"
