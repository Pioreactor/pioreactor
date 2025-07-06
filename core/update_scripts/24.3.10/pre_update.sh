#!/bin/bash

set -x
set -e

export LC_ALL=C

PIO_DIR=/home/pioreactor/.pioreactor

# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_ADDRESS=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_address)

# Check if the hostname is the LEADER_ADDRESS
if [ "$HOSTNAME.local" = "$LEADER_ADDRESS" ]; then

    # Check if the mqtt section doesn't exist in the config
    if ! crudini --get $PIO_DIR/config.ini mqtt &>/dev/null; then
        # Update MQTT configuration
        crudini --ini-options=nospace --set  $PIO_DIR/config.ini mqtt username pioreactor \
                                        --set  $PIO_DIR/config.ini mqtt password raspberry \
                                        --set  $PIO_DIR/config.ini mqtt broker_address "$LEADER_ADDRESS" \
                                        --set  $PIO_DIR/config.ini mqtt broker_port 1883 \
                                        --set  $PIO_DIR/config.ini mqtt broker_ws_port 9001 \
                                        --set  $PIO_DIR/config.ini mqtt ws_protocol ws \
                                        --set  $PIO_DIR/config.ini mqtt use_tls 0
    fi

    # this was causing bad responses from the server...
    sudo lighttpd-disable-mod compress || true
    sudo service lighttpd force-reload || true

    # rename the old contrib job files
    mv /var/www/pioreactorui/contrib/jobs/07_od_blank.yaml /var/www/pioreactorui/contrib/jobs/51_od_blank.yaml || true
    mv /var/www/pioreactorui/contrib/jobs/08_self_test.yaml /var/www/pioreactorui/contrib/jobs/50_self_test.yaml || true
    mv /var/www/pioreactorui/contrib/jobs/09_stirring_calibration.yaml /var/www/pioreactorui/contrib/jobs/52_stirring_calibration.yaml || true
fi
