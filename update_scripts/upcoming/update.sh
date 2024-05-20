#!/bin/bash

set -xeu


export LC_ALL=C


echo "force_turbo=1" | sudo tee -a /boot/config.txt

nmcli con add type ethernet con-name eth0 ifname eth0 autoconnect yes ipv4.method auto ipv6.method auto ipv6.addr-gen-mode default connection.id eth0 connection.uuid 5e55231f-ea1a-484b-88f9-88e3598c66ae connection.autoconnect-priority 1
nmcli con modify PioreactorLocalLink connection.autoconnect-priority 0 connection.autoconnect no

echo "max_inflight_messages 1000" | sudo tee /etc/mosquitto/mosquitto.conf -a
