#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
CONFIG="$DOT_PIOREACTOR/config.ini"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$($PIO_VENV/bin/crudini --get "$CONFIG" cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    sudo -u pioreactor mkdir -p "$DOT_PIOREACTOR/ui/charts"
    sudo -u pioreactor cp -f "$SCRIPT_DIR"/05_od.yaml "$DOT_PIOREACTOR/ui/charts/05_od.yaml"
fi

sudo -u pioreactor mkdir -p "$DOT_PIOREACTOR/hardware/models/pioreactor_20ml_XR/1.5"
cat <<'EOF' | sudo -u pioreactor tee "$DOT_PIOREACTOR/hardware/models/pioreactor_20ml_XR/1.5/adc.yaml" >/dev/null
pd1:
  driver: ads1114
  address: 0x49
  channel: 0
pd2:
  driver: ads1114
  address: 0x4a
  channel: 0
pd3:
  driver: ads1114
  address: 0x4b
  channel: 0
pd4:
  driver: ads1114
  address: 0x48
  channel: 0
EOF

sudo -u pioreactor mkdir -p "$DOT_PIOREACTOR/hardware/models/pioreactor_40ml_XR/1.5"
cat <<'EOF' | sudo -u pioreactor tee "$DOT_PIOREACTOR/hardware/models/pioreactor_40ml_XR/1.5/adc.yaml" >/dev/null
pd1:
  driver: ads1114
  address: 0x49
  channel: 0
pd2:
  driver: ads1114
  address: 0x4a
  channel: 0
pd3:
  driver: ads1114
  address: 0x4b
  channel: 0
pd4:
  driver: ads1114
  address: 0x48
  channel: 0
EOF

sudo -u pioreactor /opt/pioreactor/venv/bin/python "$SCRIPT_DIR"/od_calibration_device_migration.py
# Migrate curve_data_ serialization and strip legacy curve_type fields.
sudo -u pioreactor /opt/pioreactor/venv/bin/python "$SCRIPT_DIR"/calibration_curve_data_migration.py
