#!/bin/bash

set -x
set -e

export LC_ALL=C


#### Fix issue with `pio log` commands in systemd services failing

# List of systemd files
systemd_files=("/lib/systemd/system/avahi_aliases.service" "/lib/systemd/system/load_rp2040.service")

# Loop through each file and add 'User=pioreactor' and 'EnvironmentFile=/etc/environment' under '[Service]' if they don't already exist
for file in "${systemd_files[@]}"; do
    crudini --ini-options=nospace --set "$file" Service User pioreactor \
                                  --set "$file" Service EnvironmentFile "/etc/environment"
done

systemctl daemon-reload

systemctl restart avahi_aliases.service
systemctl restart load_rp2040.service
