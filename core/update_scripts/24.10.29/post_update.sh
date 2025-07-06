#!/bin/bash

set -xeu


export LC_ALL=C

sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service || :
