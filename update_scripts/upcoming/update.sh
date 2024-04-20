#!/bin/bash

# this runs at startup on every boot.

set -x
set -e

export LC_ALL=C


PIO_DIR=/home/pioreactor/.pioreactor
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # bioreactor wasn't a good choice, model is better
    for file in "$PIO_DIR"/config_*.ini; do
        crudini --ini-options=nospace --set "$file" pioreactor model pioreactor_20ml
        crudini --ini-options=nospace --del "$file" pioreactor bioreactor pioreactor_20ml

    done
    sudo -u pioreactor pios sync-configs



    # update add_new_pioreactor_worker_from_leader.sh, make sure the new version is local to this dir.
    cp ./add_new_pioreactor_worker_from_leader.sh /usr/local/bin/add_new_pioreactor_worker_from_leader.sh



    # MQTT changes
    # change MQTT config: reduce logging, and change persistance to false.
    grep -qxF 'log_type error'     /etc/mosquitto/mosquitto.conf     || echo "log_type error" | sudo tee /etc/mosquitto/mosquitto.conf -a
    grep -qxF 'log_type warning'   /etc/mosquitto/mosquitto.conf     || echo "log_type warning" | sudo tee /etc/mosquitto/mosquitto.conf -a
    grep -qxF 'log_type notice'    /etc/mosquitto/mosquitto.conf     || echo "log_type notice" | sudo tee /etc/mosquitto/mosquitto.conf -a
    grep -qxF 'persistence false'  /etc/mosquitto/mosquitto.conf     || echo "persistence false" | sudo tee /etc/mosquitto/mosquitto.conf -a

    # remove the MQTT persistance database
    rm -f /var/lib/mosquitto/mosquitto.db

    # reload the config
    kill -SIGHUP "$(cat /run/mosquitto/mosquitto.pid)"
fi




# install chrony.deb, provided locally in the release archive
sudo dpkg -i ./chrony_4.3-2+deb12u1_armhf.deb

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    if ! grep -q 'allow 10.42.0.1/24' /etc/chrony/chrony.conf; then
        echo "allow 10.42.0.1/24" | sudo tee -a /etc/chrony/chrony.conf
        sudo systemctl restart chronyd
    fi
else
    if ! grep -q 'server 10.42.0.1 iburst' /etc/chrony/chrony.conf; then
        echo "server 10.42.0.1 iburst" | sudo tee -a /etc/chrony/chrony.conf
        sudo systemctl restart chronyd
        sudo chronyc -a makestep
    fi
fi
