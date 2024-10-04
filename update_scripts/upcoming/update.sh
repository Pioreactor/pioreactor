#!/bin/bash

set -xeu


export LC_ALL=C

HUEY_SERVICE_FILE="/etc/systemd/system/huey.service"

sudo sed -i 's|-n -b 1.0 -w 2 -f -C|-n -b 1.0 -w 6 -f -C -d 0.05|' "$HUEY_SERVICE_FILE"


# Reload systemd to apply changes
sudo systemctl daemon-reload

sudo chown pioreactor:www-data /var/www/pioreactorui/__pycache__ || :
sudo chown pioreactor:www-data /var/www/pioreactorui/pioreactorui/__pycache__ || :
