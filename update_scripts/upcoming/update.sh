#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HUEY_SERVICE_FILE="/etc/systemd/system/huey.service"

# TODO: replace huey.service
mv "$SCRIPT_DIR"/huey.service $HUEY_SERVICE_FILE

# Reload systemd to apply changes
sudo systemctl daemon-reload

sudo chown pioreactor:www-data /var/www/pioreactorui/__pycache__ || :
sudo chown pioreactor:www-data /var/www/pioreactorui/pioreactorui/__pycache__ || :
