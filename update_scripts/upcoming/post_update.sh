#!/bin/bash

set -x
set -e

export LC_ALL=C


# since we are changing this mqtt-to-db job, we should restart this. This only works on leader
sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service || true
