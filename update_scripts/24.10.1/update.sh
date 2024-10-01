#!/bin/bash

set -xeu


export LC_ALL=C

HUEY_SERVICE_FILE="/etc/systemd/system/huey.service"

# mv huey to correct folder, if it's wrong
sudo mv /lib/systemd/system/huey.service "$HUEY_SERVICE_FILE" || :
# TODO: modify huey.service with the correct location

# Use sed to find and replace the line
sudo sed -i 's|ExecStart=huey_consumer tasks.huey|ExecStart=huey_consumer pioreactorui.tasks.huey|' "$HUEY_SERVICE_FILE"

# Reload systemd to apply changes
sudo systemctl daemon-reload

sudo chown pioreactor:www-data /var/www/pioreactorui/__pycache__ || :
sudo chown pioreactor:www-data /var/www/pioreactorui/pioreactorui/__pycache__ || :
