#!/bin/bash

set -xeu

export LC_ALL=C

# Serve the per-Pioreactor touchscreen UI (frontend/kiosk.html) for /k and /k/...,
# and never cache that shell. Every Pioreactor serves its own screen, so this runs
# on leaders and workers alike. Updates restart pioreactor-web.target afterwards.

UI_CONFIG="/etc/lighttpd/conf-available/50-pioreactorui.conf"
EXPIRE_CONFIG="/etc/lighttpd/conf-available/10-expire.conf"

# shellcheck disable=SC2016 # Lighttpd syntax, not shell variables.
STATIC_REWRITE='  "^(/static($|/.*))$"   => "$1",'
# shellcheck disable=SC2016
KIOSK_REWRITE='  "^/k($|[/?].*)" => "/static/kiosk.html",'
# shellcheck disable=SC2016
KIOSK_NO_STORE='$HTTP["url"] == "/static/kiosk.html" {'

log() {
    sudo -u pioreactor -i pio log -l "$1" -m "$2"
}

UI_BACKUP=$(mktemp)
EXPIRE_BACKUP=$(mktemp)
UI_TEMP=""
EXPIRE_TEMP=""
trap 'rm -f "$UI_BACKUP" "$EXPIRE_BACKUP" "${UI_TEMP:-}" "${EXPIRE_TEMP:-}"' EXIT

changed=0

if [ ! -f "$UI_CONFIG" ]; then
    log WARNING "No lighttpd UI configuration was found at $UI_CONFIG. The /k/ touchscreen route was not installed."
elif ! grep -Fq "/static/kiosk.html" "$UI_CONFIG"; then
    if grep -Fxq "$STATIC_REWRITE" "$UI_CONFIG"; then
        cp -p "$UI_CONFIG" "$UI_BACKUP"
        UI_TEMP=$(mktemp "$(dirname "$UI_CONFIG")/.50-pioreactorui.conf.XXXXXX")
        awk -v anchor="$STATIC_REWRITE" -v rule="$KIOSK_REWRITE" '
            { print }
            $0 == anchor && !done {
                print "  # The per-Pioreactor touchscreen UI loads its own HTML entry for /k and /k/..."
                print rule
                done = 1
            }
        ' "$UI_CONFIG" > "$UI_TEMP"
        chown root:root "$UI_TEMP"
        chmod 0644 "$UI_TEMP"
        mv "$UI_TEMP" "$UI_CONFIG"
        UI_TEMP=""
        changed=1
    else
        log WARNING "Preserving customized lighttpd UI configuration at $UI_CONFIG. The /k/ touchscreen route was not installed."
    fi
fi

if [ ! -f "$EXPIRE_CONFIG" ]; then
    log WARNING "No lighttpd cache configuration was found at $EXPIRE_CONFIG. The touchscreen shell no-store policy was not installed."
elif ! grep -Fq "$KIOSK_NO_STORE" "$EXPIRE_CONFIG"; then
    cp -p "$EXPIRE_CONFIG" "$EXPIRE_BACKUP"
    EXPIRE_TEMP=$(mktemp "$(dirname "$EXPIRE_CONFIG")/.10-expire.conf.XXXXXX")
    cp -p "$EXPIRE_CONFIG" "$EXPIRE_TEMP"
    cat >> "$EXPIRE_TEMP" <<'CONF'

# The touchscreen UI's shell (frontend/kiosk.html, served for /k/...). Like the SPA
# shell, a cached copy would keep pointing at hashed assets an update removed.
$HTTP["url"] == "/static/kiosk.html" {
    setenv.set-response-header = (
        "Cache-Control" => "no-store, max-age=0"
    )
}
CONF
    chown root:root "$EXPIRE_TEMP"
    chmod 0644 "$EXPIRE_TEMP"
    mv "$EXPIRE_TEMP" "$EXPIRE_CONFIG"
    EXPIRE_TEMP=""
    changed=1
fi

[ "$changed" -eq 1 ] || exit 0

if ! /usr/sbin/lighttpd -tt -f /etc/lighttpd/lighttpd.conf; then
    [ -s "$UI_BACKUP" ] && install -o root -g root -m 0644 "$UI_BACKUP" "$UI_CONFIG"
    [ -s "$EXPIRE_BACKUP" ] && install -o root -g root -m 0644 "$EXPIRE_BACKUP" "$EXPIRE_CONFIG"
    log ERROR "Unable to validate the lighttpd touchscreen configuration. The previous configuration was restored."
    exit 1
fi
