#!/bin/bash

set -xeu


export LC_ALL=C

LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)


sudo systemctl stop pioreactor_startup_run@monitor.service || :
sudo systemctl stop pioreactor_startup_run@mqtt_to_db_streaming.service || :

sudo rm /tmp/pioreactor_cache/local_intermittent_pioreactor_metadata.sqlite || :

sudo systemctl restart create_diskcache.service || :

sudo systemctl start pioreactor_startup_run@monitor.service || :
sudo systemctl start pioreactor_startup_run@mqtt_to_db_streaming.service || :
