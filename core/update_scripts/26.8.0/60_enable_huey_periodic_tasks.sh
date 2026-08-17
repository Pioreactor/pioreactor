#!/bin/bash

set -xeu

export LC_ALL=C

remove_huey_no_periodic_flag() {
    local path="$1"

    [ -f "$path" ] || return 0

    sed -E -i '/huey_consumer/ s/(^|[[:space:]])(-n|--no-periodic)([[:space:]]|$)/ /g' "$path"

    if grep -Eq 'huey_consumer.*[[:space:]](-n|--no-periodic)([[:space:]]|$)' "$path"; then
        echo "Unable to enable Huey periodic tasks in $path." >&2
        exit 1
    fi
}

# Older installations launch Huey directly from the systemd unit. Newer images
# use the launcher script, so update both paths to preserve the same invariant.
remove_huey_no_periodic_flag /etc/systemd/system/huey.service
remove_huey_no_periodic_flag /lib/systemd/system/huey.service
remove_huey_no_periodic_flag /usr/local/bin/start_pioreactor_huey.sh

systemctl daemon-reload
