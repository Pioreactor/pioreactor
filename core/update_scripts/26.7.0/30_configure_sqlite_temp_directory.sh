#!/bin/bash

set -xeu

export LC_ALL=C

ENV_FILE=/etc/pioreactor.env
SQLITE_TEMP_DIRECTORY=/var/tmp/pioreactor
tmp="$(mktemp "${ENV_FILE}.XXXXXX")"

clean_up() {
    if [ -n "$tmp" ]; then
        rm -f "$tmp"
    fi
}

trap clean_up EXIT

install -d -o pioreactor -g www-data -m 2770 "$SQLITE_TEMP_DIRECTORY"

awk -v sqlite_temp_directory="$SQLITE_TEMP_DIRECTORY" '
    BEGIN {
        configured = 0
    }

    /^SQLITE_TMPDIR=/ {
        if (!configured) {
            print "SQLITE_TMPDIR=" sqlite_temp_directory
            configured = 1
        }
        next
    }

    {
        print
    }

    END {
        if (!configured) {
            print "SQLITE_TMPDIR=" sqlite_temp_directory
        }
    }
' "$ENV_FILE" > "$tmp"

chown root:root "$tmp"
chmod 0644 "$tmp"
mv "$tmp" "$ENV_FILE"
tmp=""
