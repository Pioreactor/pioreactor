#!/bin/bash

set -x
set -e

export LC_ALL=C

# since we are changing the db, we should restart this. This only works on leader
sudo systemctl restart pioreactor_startup_run@monitor.service
