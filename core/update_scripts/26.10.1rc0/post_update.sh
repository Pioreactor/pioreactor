#!/bin/bash

set -xeu

export LC_ALL=C

UNIT_HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

# Load the channel-keyed subscription after installing the new app. Worker jobs
# must be restarted by the operator as part of the coordinated cluster upgrade.
if [ "$UNIT_HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service
fi
