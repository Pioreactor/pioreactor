#!/bin/bash

source /etc/pioreactor.env 2>/dev/null || true
VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"
PIO="$VENV_BIN/pio"

# Retrieve the domain alias from the configuration file
DOMAIN_ALIAS=$(sudo -u pioreactor "$PIO" config get ui domain_alias)

# Function to publish mDNS for each IP
publish_mdns() {
    local ip=$1
    echo "Publishing mDNS for $DOMAIN_ALIAS at IP $ip"
    /usr/bin/avahi-publish -a -R "$DOMAIN_ALIAS" "$ip" || true &
}

# Get all IP addresses, ignoring localhost
while :; do
    IP_ADDRESSES=$(hostname -I | grep -Eo '([0-9]*\.){3}[0-9]*' | tr '\n' '\n')

    if [ -n "$IP_ADDRESSES" ]; then
        break
    fi

    echo "Waiting for a valid network interface..."
    sleep 2
done

# Iterate over each IP and publish mDNS
for IP in $IP_ADDRESSES; do
    publish_mdns "$IP"
done
