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
    install -o pioreactor -g www-data -m 0664 "$src" "$tmp"
    install -d -o pioreactor -g www-data -m 2775 "$(dirname "$dst")"
    mv "$tmp" "$dst"

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
}

remove_legacy_builtin_descriptors() {
    rm -f \
        "$DOT_PIOREACTOR/ui/automations/dosing/chemostat.yaml" \
        "$DOT_PIOREACTOR/ui/automations/dosing/turbidostat.yaml" \
        "$DOT_PIOREACTOR/ui/automations/dosing/fed_batch.yaml" \
        "$DOT_PIOREACTOR/ui/automations/dosing/pid_morbidostat.yaml" \
        "$DOT_PIOREACTOR/ui/automations/dosing/silent.yaml" \
        "$DOT_PIOREACTOR/ui/automations/led/light_dark_cycle.yaml" \
        "$DOT_PIOREACTOR/ui/automations/led/silent.yaml" \
        "$DOT_PIOREACTOR/ui/bioreactor.yaml" \
        "$DOT_PIOREACTOR/ui/jobs/05_leds.yaml" \
        "$DOT_PIOREACTOR/ui/jobs/13_pwms.yaml"
}

remove_legacy_builtin_descriptors

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
install_checked_asset \
    "$SCRIPT_DIR/ui_settings_00_bioreactor.yaml" \
    "$DOT_PIOREACTOR/ui/settings/00_bioreactor.yaml"
install_checked_asset \
    "$SCRIPT_DIR/ui_settings_05_leds.yaml" \
    "$DOT_PIOREACTOR/ui/settings/05_leds.yaml"
install_checked_asset \
    "$SCRIPT_DIR/ui_settings_13_pwms.yaml" \
    "$DOT_PIOREACTOR/ui/settings/13_pwms.yaml"
