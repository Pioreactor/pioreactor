#!/bin/bash

set -x
set -e

export LC_ALL=C

PIO_DIR=/home/pioreactor/.pioreactor


# update MQTT configuration
LEADER_ADDRESS=$(crudini --get $PIO_DIR/config.ini cluster.inventory leader_address)

crudini --ini-options=nospace --set  $PIO_DIR/config.ini mqtt username pioreactor \
                              --set  $PIO_DIR/config.ini mqtt password raspberry \
                              --set  $PIO_DIR/config.ini mqtt broker_address "$LEADER_ADDRESS" \
                              --set  $PIO_DIR/config.ini mqtt broker_port 9001
