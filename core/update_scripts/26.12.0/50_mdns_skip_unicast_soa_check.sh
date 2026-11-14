#!/bin/bash

set -xeu

export LC_ALL=C

# nss-mdns's mdns4_minimal asks unicast DNS for a `local.` SOA before every .local lookup, which costs a DNS
# round trip (~20 ms on a typical LAN) on every broker connect and every request to a Pioreactor. mdns4 skips
# that query when /etc/mdns.allow exists. Tradeoff: IPv4 reverse lookups (IP -> name) of non-mDNS hosts stall
# ~5 s, e.g. `ping -4` without -n.
#
# Only the stock Debian hosts line is changed, so a user's customized nsswitch.conf is left alone.
NSSWITCH=/etc/nsswitch.conf
MDNS_ALLOW=/etc/mdns.allow
STOCK_HOSTS_RE='^hosts:[[:space:]]+files[[:space:]]+mdns4_minimal[[:space:]]+\[NOTFOUND=return\][[:space:]]+dns[[:space:]]*$'
NEW_HOSTS_LINE='hosts:          files mdns4 [NOTFOUND=return] dns'

[ -f "$NSSWITCH" ] || exit 0
grep -Eq "$STOCK_HOSTS_RE" "$NSSWITCH" || exit 0

# mdns4 only resolves names listed in mdns.allow, so an existing file without .local would break .local lookups.
if [ -f "$MDNS_ALLOW" ] && ! grep -Eq '^\.local\.?[[:space:]]*$' "$MDNS_ALLOW"; then
    exit 0
fi

if [ ! -f "$MDNS_ALLOW" ]; then
    tmp="$(mktemp)"
    printf ".local.\n.local\n" > "$tmp"
    chmod 0644 "$tmp"
    mv "$tmp" "$MDNS_ALLOW"
fi

cp -p "$NSSWITCH" "$NSSWITCH.bak-mdns4"
tmp="$(mktemp)"
sed -E "s/$STOCK_HOSTS_RE/$NEW_HOSTS_LINE/" "$NSSWITCH" > "$tmp"
chmod --reference="$NSSWITCH" "$tmp"
mv "$tmp" "$NSSWITCH"

# Postcondition: this host's own .local name still resolves through avahi. Restore the stock line if not.
if ! getent ahostsv4 "$(hostname).local" > /dev/null; then
    mv "$NSSWITCH.bak-mdns4" "$NSSWITCH"
    echo "Resolving $(hostname).local failed after switching to mdns4; restored $NSSWITCH." >&2
    exit 0
fi
