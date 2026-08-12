#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BOOT_CONFIG_PATH="/boot/firmware/config.txt"

if [ ! -f "$BOOT_CONFIG_PATH" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Unable to set gpu_mem: no config.txt was found."
    exit 1
fi

if grep -Eq '^[[:space:]]*gpu_mem[[:space:]]*=' "$BOOT_CONFIG_PATH"; then
    sed -i 's/^[[:space:]]*gpu_mem[[:space:]]*=.*$/gpu_mem=32/' "$BOOT_CONFIG_PATH"
else
    printf '\n[all]\ngpu_mem=32\n' >> "$BOOT_CONFIG_PATH"
fi

bash "$SCRIPT_DIR/20_install_libtiff_runtime.sh"
bash "$SCRIPT_DIR/30_add_camera_config.sh"
bash "$SCRIPT_DIR/40_install_self_test_ui_job.sh"
