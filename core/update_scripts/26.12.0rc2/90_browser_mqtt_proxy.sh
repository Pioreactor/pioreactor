#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG=/etc/lighttpd/conf-available/50-pioreactorui.conf
ASSET="$SCRIPT_DIR/browser-mqtt-proxy.conf"
[ -s "$ASSET" ] || { echo 'Missing browser MQTT proxy asset' >&2; exit 1; }
[ -f "$CONFIG" ] || { echo "Missing $CONFIG" >&2; exit 1; }

# Inspect the effective config, including modules loaded by other include files.
# -tt alone succeeds with warnings when proxy.* directives have no owning module.
proxy_module_loaded() {
    local effective_config
    effective_config=$(/usr/sbin/lighttpd -p -f /etc/lighttpd/lighttpd.conf) || return 1
    printf '%s\n' "$effective_config" | awk '
        /server\.modules[[:space:]]*=/ { in_modules = 1 }
        in_modules && /"mod_proxy"/ { found = 1 }
        in_modules && /\)/ { in_modules = 0 }
        END { exit !found }
    '
}

BACKUP=$(mktemp)
TEMP=$(mktemp "${CONFIG}.XXXXXX")
cp -p "$CONFIG" "$BACKUP"
trap 'rm -f "$BACKUP" "$TEMP"' EXIT
# Only amend the known SPA exclusion; do not replace customized routing wholesale.
if grep -Fq '|/mqtt$)' "$CONFIG"; then
    cp "$CONFIG" "$TEMP"
else
    if ! grep -Fq '|/exports($|/))' "$CONFIG"; then
        echo 'Unrecognized SPA routing; configure /mqtt before updating the frontend.' >&2
        exit 1
    fi
    # Match the literal dollar sign in the route on both GNU and BSD sed.
    sed 's@|/exports(\$|/))@|/exports($|/)|/mqtt$)@' "$CONFIG" > "$TEMP"
fi

# Repair the proxy block independently of the SPA exclusion so retries cannot duplicate it.
# shellcheck disable=SC2016
if ! grep -Fq '$HTTP["url"] == "/mqtt" {' "$TEMP"; then
    cat "$ASSET" >> "$TEMP"
fi

if ! proxy_module_loaded; then
    printf '\nserver.modules += ( "mod_proxy" )\n' >> "$TEMP"
fi
chmod 0644 "$TEMP"
chown root:root "$TEMP"
mv "$TEMP" "$CONFIG"
if ! /usr/sbin/lighttpd -tt -f /etc/lighttpd/lighttpd.conf || ! proxy_module_loaded; then
    cp -p "$BACKUP" "$CONFIG"
    echo 'MQTT proxy configuration failed validation; restored previous configuration.' >&2
    exit 1
fi
