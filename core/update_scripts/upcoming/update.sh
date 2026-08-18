#!/bin/bash

set -xeu

export LC_ALL=C

ENV_FILE=/etc/pioreactor.env
LARGE_TEMP_DIRECTORY=/var/tmp/pioreactor
tmp="$(mktemp "${ENV_FILE}.XXXXXX")"

clean_up() {
    if [ -n "$tmp" ]; then
        rm -f "$tmp"
    fi
}

trap clean_up EXIT

install -d -o pioreactor -g www-data -m 2770 "$LARGE_TEMP_DIRECTORY"

awk -v large_temp_directory="$LARGE_TEMP_DIRECTORY" '
    BEGIN {
        configured = 0
    }

    /^PIOREACTOR_LARGE_TMPDIR=/ {
        if (!configured) {
            print "PIOREACTOR_LARGE_TMPDIR=" large_temp_directory
            configured = 1
        }
        next
    }

    {
        print
    }

    END {
        if (!configured) {
            print "PIOREACTOR_LARGE_TMPDIR=" large_temp_directory
        }
    }
' "$ENV_FILE" > "$tmp"

chown root:root "$tmp"
chmod 0644 "$tmp"
mv "$tmp" "$ENV_FILE"
tmp=""
