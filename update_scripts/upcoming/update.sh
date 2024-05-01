#!/bin/bash

# this runs at startup on every boot.

set -xeu


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
        crudini --ini-options=nospace --del "$file" pioreactor bioreactor 2>/dev/null || true

    done
    sudo -u pioreactor pios sync-configs || :

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
sudo dpkg -i ./chrony_4.3-2+deb12u1_armhf.deb || sudo apt-get install -y chrony
LEADER_ADDRESS=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_address)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
    if ! grep -q 'allow all' /etc/chrony/chrony.conf; then
        echo "allow all" | sudo tee -a /etc/chrony/chrony.conf
        echo "local stratum 10" | sudo tee -a /etc/chrony/chrony.conf
        sudo systemctl restart chronyd
    fi
else
    if ! grep -q "server $LEADER_ADDRESS iburst prefer" /etc/chrony/chrony.conf; then
        echo "server $LEADER_ADDRESS iburst prefer" | sudo tee -a /etc/chrony/chrony.conf
        sudo systemctl restart chronyd
        sudo chronyc -a makestep
    fi
fi
