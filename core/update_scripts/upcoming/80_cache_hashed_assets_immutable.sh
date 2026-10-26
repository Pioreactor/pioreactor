#!/bin/bash

set -xeu

export LC_ALL=C

# Files under /static/static/ have content-hashed names, so browsers can cache them forever
# instead of revalidating every 12 hours.
# Runs on every unit, not only the leader: roles are set by config and can change later.
LIGHTTPD_CONFIG="/etc/lighttpd/conf-available/10-expire.conf"
# shellcheck disable=SC2016 # Lighttpd syntax, not a shell variable.
HASHED_ASSETS_BLOCK='$HTTP["url"] =~ "^/static/static/" {'
NEW_POLICY='        "Cache-Control" => "public, max-age=31536000, immutable"'

if [ ! -f "$LIGHTTPD_CONFIG" ]; then
    exit 0
fi

if grep -Fq "$NEW_POLICY" "$LIGHTTPD_CONFIG"; then
    exit 0
fi

# Units that never ran 26.8.0's leader-only SPA shell migration still have a broad "^/static/"
# block that also matches index.html. Making that block immutable would pin the SPA shell, so skip.
if ! grep -Fq "$HASHED_ASSETS_BLOCK" "$LIGHTTPD_CONFIG"; then
    exit 0
fi

TEMP_CONFIG=$(mktemp "$(dirname "$LIGHTTPD_CONFIG")/.10-expire.conf.XXXXXX")
BACKUP_CONFIG=$(mktemp)
RESTORE_CONFIG=""
trap 'rm -f "$TEMP_CONFIG" "$BACKUP_CONFIG" "${RESTORE_CONFIG:-}"' EXIT

cp -p "$LIGHTTPD_CONFIG" "$BACKUP_CONFIG"

if ! awk '
    {
        lines[NR] = $0
    }
    END {
        start = "$HTTP[\"url\"] =~ \"^/static/static/\" {"
        old_policy = "    expire.url = ( \"\" => \"access 12 hours\" )"

        for (line_number = 1; line_number <= NR; line_number++) {
            if (lines[line_number] == start) {
                in_block = 1
                print lines[line_number]
            } else if (in_block && lines[line_number] == old_policy) {
                print "    setenv.set-response-header = ("
                print "        \"Cache-Control\" => \"public, max-age=31536000, immutable\""
                print "    )"
                replaced = 1
                in_block = 0
            } else {
                if (lines[line_number] == "}") {
                    in_block = 0
                }
                print lines[line_number]
            }
        }

        if (!replaced) {
            exit 42
        }
    }
' "$LIGHTTPD_CONFIG" > "$TEMP_CONFIG"; then
    sudo -u pioreactor -i pio log -l WARNING -m "Preserving customized lighttpd cache configuration at $LIGHTTPD_CONFIG. The long-lived cache policy for hashed assets was not installed."
    exit 0
fi

chown root:root "$TEMP_CONFIG"
chmod 0644 "$TEMP_CONFIG"
mv "$TEMP_CONFIG" "$LIGHTTPD_CONFIG"

if ! /usr/sbin/lighttpd -tt -f /etc/lighttpd/lighttpd.conf; then
    RESTORE_CONFIG=$(mktemp "$(dirname "$LIGHTTPD_CONFIG")/.10-expire.conf.XXXXXX")
    install -o root -g root -m 0644 "$BACKUP_CONFIG" "$RESTORE_CONFIG"
    mv "$RESTORE_CONFIG" "$LIGHTTPD_CONFIG"
    sudo -u pioreactor -i pio log -l ERROR -m "Unable to validate the lighttpd cache policy for hashed assets. The previous configuration was restored."
    exit 1
fi

grep -Fq "$NEW_POLICY" "$LIGHTTPD_CONFIG"
