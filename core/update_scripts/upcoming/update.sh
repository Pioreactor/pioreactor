#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/10_huey_idle_polling_backoff.sh"
bash "$SCRIPT_DIR/20_ir_led_intensity_auto_to_80.sh"
