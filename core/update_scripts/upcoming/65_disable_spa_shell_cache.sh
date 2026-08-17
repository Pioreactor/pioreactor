#!/bin/bash

set -xeu

export LC_ALL=C

HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

LIGHTTPD_CONFIG="/etc/lighttpd/conf-available/10-expire.conf"
# shellcheck disable=SC2016 # Lighttpd syntax, not a shell variable.
SPA_ROUTE_POLICY='$HTTP["url"] !~ "^(/api($|/)|/api\.fcgi($|/)|/unit_api($|/)|/mcp($|/)|/static($|/)|/exports($|/))" {'

if [ ! -f "$LIGHTTPD_CONFIG" ]; then
    sudo -u pioreactor -i pio log -l WARNING -m "No lighttpd cache configuration was found at $LIGHTTPD_CONFIG. The SPA shell no-store policy was not installed."
    exit 0
fi

if grep -Fq "$SPA_ROUTE_POLICY" "$LIGHTTPD_CONFIG"; then
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
        old_static_start = "$HTTP[\"url\"] =~ \"^/static/\" {"
        old_start = "$HTTP[\"url\"] == \"/static/index.html\" {"
        old_policy = "    expire.url = ( \"\" => \"access 0 seconds\" )"

        for (line_number = 1; line_number <= NR; line_number++) {
            if (lines[line_number] == old_static_start) {
                print "$HTTP[\"url\"] =~ \"^/static/static/\" {"
                narrowed_static_cache = 1
            } else if (lines[line_number] == old_start &&
                lines[line_number + 1] == old_policy &&
                lines[line_number + 2] == "}") {
                print "$HTTP[\"url\"] !~ \"^(/api($|/)|/api\\.fcgi($|/)|/unit_api($|/)|/mcp($|/)|/static($|/)|/exports($|/))\" {"
                print "    setenv.set-response-header = ("
                print "        \"Cache-Control\" => \"no-store, max-age=0\""
                print "    )"
                print "}"
                print ""
                print old_start
                print "    setenv.set-response-header = ("
                print "        \"Cache-Control\" => \"no-store, max-age=0\""
                print "    )"
                print "}"
                line_number += 2
                replaced = 1
            } else {
                print lines[line_number]
            }
        }

        if (!replaced || !narrowed_static_cache) {
            exit 42
        }
    }
' "$LIGHTTPD_CONFIG" > "$TEMP_CONFIG"; then
    sudo -u pioreactor -i pio log -l WARNING -m "Preserving customized lighttpd cache configuration at $LIGHTTPD_CONFIG. The SPA shell no-store policy was not installed."
    exit 0
fi

chown root:root "$TEMP_CONFIG"
chmod 0644 "$TEMP_CONFIG"
mv "$TEMP_CONFIG" "$LIGHTTPD_CONFIG"

if ! /usr/sbin/lighttpd -tt -f /etc/lighttpd/lighttpd.conf; then
    RESTORE_CONFIG=$(mktemp "$(dirname "$LIGHTTPD_CONFIG")/.10-expire.conf.XXXXXX")
    install -o root -g root -m 0644 "$BACKUP_CONFIG" "$RESTORE_CONFIG"
    mv "$RESTORE_CONFIG" "$LIGHTTPD_CONFIG"
    sudo -u pioreactor -i pio log -l ERROR -m "Unable to validate the lighttpd SPA shell cache policy. The previous configuration was restored."
    exit 1
fi

grep -Fq "$SPA_ROUTE_POLICY" "$LIGHTTPD_CONFIG"
