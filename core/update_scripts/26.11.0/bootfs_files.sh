#!/bin/bash

set -eu
export LC_ALL=C

# Run after firstboot/everyboot. Unconfigured workers keep staged assets until
# cluster onboarding delivers config.ini and reboots them.
# shellcheck source=/dev/null
source /etc/pioreactor.env
DOT_PIOREACTOR="${DOT_PIOREACTOR:-/home/pioreactor/.pioreactor}"
export DOT_PIOREACTOR
[ -f "$DOT_PIOREACTOR/config.ini" ] || exit 0

leader_hostname=$(timeout --kill-after=5 30 sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
[ -n "$leader_hostname" ] || exit 1
role=worker
if [ "$leader_hostname" = "$(hostname)" ]; then
    role=leader
fi

export SKIP_PLUGINS=1
exec "${PIO_VENV:-/opt/pioreactor/venv}/bin/python" -m pioreactor.boot_files "$role"
