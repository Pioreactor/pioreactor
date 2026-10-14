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

# Each unit now stores its own model, rather than asking the leader on every lookup. Copy the
# leader's record once (a no-op if this unit already has one, or isn't in the inventory). The
# leader's web server may be restarting during a cluster update, so retry for about a minute.
MODEL_ADOPTED=0
for _ in $(seq 1 12); do
    if sudo -u pioreactor -i pio model adopt; then
        MODEL_ADOPTED=1
        break
    fi
    sleep 5
done
if [ "$MODEL_ADOPTED" = 0 ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Unable to copy this unit's model from the leader. Run \`pio model adopt\` once the leader is reachable." || :
fi



# Retained bioreactor values were published as bare floats; republish them as timestamped
# payloads so restarted dosing automations and the UI can decode them.
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python - <<'PYTHON' || :
from pioreactor import bioreactor
from pioreactor.pubsub import create_client
from pioreactor.whoami import get_assigned_experiment_name, get_unit_name

unit = get_unit_name()
experiment = get_assigned_experiment_name(unit)
with create_client() as client:
    for variable_name, value in bioreactor.get_all_bioreactor_values(experiment).items():
        bioreactor.publish_bioreactor_value(client, unit, experiment, variable_name, value)
PYTHON
