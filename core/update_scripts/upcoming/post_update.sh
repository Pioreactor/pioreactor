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

# Best-effort adoption from the existing leader; disconnected updates still succeed.
# The runtime retries adoption on its first successful leader model lookup.
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python -c 'from pioreactor.unit_model import adopt_model_from_leader; adopt_model_from_leader()' || :

# Retained bioreactor values were published as bare floats; republish them as timestamped
# payloads so restarted dosing automations and the UI can decode them.
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python -c '
from pioreactor import bioreactor
from pioreactor.pubsub import create_client
from pioreactor.whoami import get_assigned_experiment_name, get_unit_name

unit = get_unit_name()
experiment = get_assigned_experiment_name(unit)
with create_client() as client:
    for variable_name, value in bioreactor.get_all_bioreactor_values(experiment).items():
        bioreactor.publish_bioreactor_value(client, unit, experiment, variable_name, value)
' || :
