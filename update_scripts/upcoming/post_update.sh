#!/bin/bash

set -x
set -e

export LC_ALL=C


# since we are changing the db, we should restart this
sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service

# TODO: run a python script to convert existing calibrations to the new style
wget -O /tmp/convert_calibrations.py http://...
python3 /tmp/convert_calibrations.py
