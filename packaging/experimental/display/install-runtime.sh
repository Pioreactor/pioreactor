#!/bin/sh
# CustoPiZer build-time install, inside the ARM64 image chroot. Never starts services.
set -eu
assets=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
bundle=$assets
runtime=/opt/pioreactor-display/rootfs
[ "$(dpkg --print-architecture)" = arm64 ] || { echo 'Display requires ARM64.' >&2; exit 1; }
(cd "$bundle" && sha256sum --check runtime.sha256)
[ ! -e "$runtime" ] || { echo "$runtime already exists; refusing to overwrite an installed runtime." >&2; exit 1; }
if getent passwd pioreactor-display >/dev/null || getent group pioreactor-display >/dev/null; then
    echo 'Existing pioreactor-display account/group found; refusing to modify it.' >&2
    exit 1
fi
for group in video render input; do
    getent group "$group" >/dev/null || groupadd --system "$group"
done
mkdir -p /opt/pioreactor-display
stage=$(mktemp -d /opt/pioreactor-display/.install.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT HUP INT TERM
tar --extract --gzip --numeric-owner --file "$bundle/runtime.tar.gz" --directory "$stage"
mkdir -p "$stage/dev" "$stage/proc" "$stage/sys" "$stage/run" "$stage/tmp" "$stage/root" "$stage/home" "$stage/var/log" "$stage/var/lib/apt/lists/partial" "$stage/var/cache/apt/archives/partial"
chmod 1777 "$stage/tmp"
chmod 700 "$stage/root"
mknod -m 666 "$stage/dev/null" c 1 3
mknod -m 666 "$stage/dev/zero" c 1 5
mknod -m 666 "$stage/dev/random" c 1 8
mknod -m 666 "$stage/dev/urandom" c 1 9
install -m644 "$bundle/patches/libnss-mdns_0.15.1-5+b1_arm64.deb" "$stage/tmp/libnss-mdns.deb"
chroot "$stage" dpkg -i /tmp/libnss-mdns.deb
rm "$stage/tmp/libnss-mdns.deb"
python3 "$assets/install-cursor-aliases.py" "$stage"
install -Dm755 "$bundle/patches/libpioreactor-drm-cursor-fix.so" "$stage/usr/local/lib/libpioreactor-drm-cursor-fix.so"
install -Dm644 "$assets/src/drm-cursor-fix.c" "$stage/usr/local/src/pioreactor-display/src/drm-cursor-fix.c"
install -m644 "$assets/Makefile" "$stage/usr/local/src/pioreactor-display/Makefile"
# Choose IDs free in both the host and the packaged userspace.
uid=600
while :; do
    host_entry=$(getent passwd "$uid" || true)
    inner_entry=$(chroot "$stage" getent passwd "$uid" || true)
    case "$inner_entry" in pioreactor-display:*|'') inner_free=true ;; *) inner_free=false ;; esac
    if [ -z "$host_entry" ] && [ "$inner_free" = true ]; then break; fi
    uid=$((uid + 1))
    [ "$uid" -lt 1000 ] || { echo 'No free system UID.' >&2; exit 1; }
done
gid=600
while :; do
    host_entry=$(getent group "$gid" || true)
    inner_entry=$(chroot "$stage" getent group "$gid" || true)
    case "$inner_entry" in pioreactor-display:*|'') inner_free=true ;; *) inner_free=false ;; esac
    if [ -z "$host_entry" ] && [ "$inner_free" = true ]; then break; fi
    gid=$((gid + 1))
    [ "$gid" -lt 1000 ] || { echo 'No free system GID.' >&2; exit 1; }
done
chroot "$stage" groupmod --gid "$gid" pioreactor-display
chroot "$stage" usermod --uid "$uid" --gid "$gid" pioreactor-display
cp -L /etc/resolv.conf "$stage/etc/resolv.conf"
# Bind the host machine ID at runtime; do not bake a shared identity into images.
: > "$stage/etc/machine-id"
mkdir -p "$stage/var/lib/dbus"
ln -sf /etc/machine-id "$stage/var/lib/dbus/machine-id"
install -m755 "$assets/start-pioreactor-display" "$stage/usr/local/bin/start-pioreactor-display"
chroot "$stage" /usr/local/bin/pioreactor-display --version
groupadd --system --gid "$gid" pioreactor-display
useradd --system --uid "$uid" --gid "$gid" --home-dir /var/lib/pioreactor-display --shell /usr/sbin/nologin pioreactor-display
mv "$stage" "$runtime"
trap - EXIT HUP INT TERM
install -m644 "$assets/pioreactor-display.service" /etc/systemd/system/pioreactor-display.service
if [ ! -e /etc/default/pioreactor-display ]; then
    install -m644 "$assets/display.env" /etc/default/pioreactor-display
fi
install -m755 "$assets/smoke-test.sh" /usr/local/bin/pioreactor-display-smoke-test
