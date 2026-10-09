# Experimental HDMI display (ARM64 leaders)

WPE 2.54.0 displays the local Pioreactor UI directly through DRM/KMS, without a
desktop or compositor. This is experimental. The supplied bundle was tested on
xr1 (Pi 4, 1 GB RAM); other models, touch input, and fresh image boots still need
validation.

CustoPiZer syncs this directory and runs `08-install-display.sh` only when
`LEADER=1` and the image architecture is `arm64`. Leader and leader-worker images
preinstall the runtime; worker-only and 32-bit images do not install it. The
generic Linux leader installer does not consume this feature.

## Enable and disable

1. Create an empty file named exactly `experimental_display` on bootfs
   (`/boot/firmware/experimental_display` on the Pi).
2. Connect an HDMI monitor and USB mouse, then boot.
3. If `experimental_display.log` appears on bootfs, reboot once more to apply
   the staged HDMI configuration. The helper does not reboot automatically.

Removing the flag and rebooting stops activation and restores the console. If
HDMI settings changed, reboot once more to restore the image's original HDMI
configuration. The flag is persistent, not consumed. Its contents are ignored.
Do not create a directory or a file named `experimental_display.txt` instead.

The browser starts only after the boot helper has confirmed the selected HDMI
configuration was already staged. It waits for a connected DRM display and a
successful response from the display UI, `http://localhost/static/display.html`.
That page is a lean, touch-first UI built from `frontend/display.html` for small
landscape screens (designed at 800x480); the full web UI stays at `/` for other
computers. The boot helper stops the tty1
login prompt only when display activation is ready. No browser process runs
without the flag. This controls startup, not live removal of the flag.

CustoPiZer moves the original VC4 overlay, HDMI blanking and EDID overrides into
`/etc/pioreactor-display/headless.txt`, and creates `display.txt` with the standard
VC4 KMS overlay. `/boot/firmware/config.txt` includes the managed
`pioreactor-display.txt`. Do not edit that generated include; it is replaced on
boot when switching modes. Other boot settings remain in config.txt.

## Runtime and maintenance

These files were extracted from `pioreactor-display-arm64-wpe-2.54.0.tar`:

- `runtime.tar.gz`: the isolated ARM64 Debian userspace, including WPE and its
  dependencies. It is required for offline image builds (about 403 MiB compressed).
- `patches/`: the tested cursor-coordinate interposer and libnss-mdns package.
- `src/`, `Makefile`, and `start-pioreactor-display`: launcher and patch source.
- `runtime-packages.txt` and `BUNDLE-NOTES.txt`: original provenance and test notes.

`runtime.sha256` pins the three binary inputs. No bundle downloads occur.
The runtime archive exceeds GitHub's ordinary Git file-size limit; decide on
large-file storage before pushing it. The local build consumes the extracted
archive directly, without needing the original outer tar file.

`install-runtime.sh` is for the image-build chroot, not a running-device
installer. It verifies checksums, installs under `/opt/pioreactor-display/rootfs`,
applies the cursor and mDNS fixes, and creates a dedicated account. It never
starts services. The host's machine ID, DNS configuration, and Avahi socket are
exposed to the runtime at service start; image builds do not generate a shared
machine identity. Package copyright/license files remain inside the runtime.

Host apt updates do not update this isolated browser runtime. Rebuild and retest
it for browser/security updates; update binary checksums with replacement inputs.
Allow at least 1.5 GB extra image-build space for the extracted runtime, in
addition to the compressed build input.

Settings: `/etc/default/pioreactor-display` (restart the display service after
changing). Diagnostics:

```sh
sudo systemctl status pioreactor-display-boot pioreactor-display
sudo journalctl -u pioreactor-display-boot -u pioreactor-display -b
sudo pioreactor-display-smoke-test
```

The smoke test checks off-screen rendering of the local display UI; it does not
prove HDMI, mouse, touch, or boot gating. Image acceptance should exercise both
leader targets, verify worker exclusion, boot without the flag, add the flag and
reboot as directed, then remove it and confirm console/headless restoration.

Use CustoPiZer's `config_64.local` and an ARM64 Raspberry Pi OS base image for
these builds, for example `bash make_leader_worker_image.sh <version>
"$(pwd)/config_64.local"`. That config reserves extra temporary build space; the
normal image minimization still runs afterward. The current release workflow
uses an ARMHF base and therefore skips this feature; the ARM64 nightly path
uses `config_64.local`.
