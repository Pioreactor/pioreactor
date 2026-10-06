# Packaging

This directory contains files used to build or install Pioreactor outside the normal Python package runtime. Most files here are provisioning inputs: they seed databases, config directories, system services, or image-builder workspaces.

## Directories

- `shared-assets/`: one-time provisioning seed data shared by Linux installs and CustoPiZer image builds, including SQL, config, camera tuning, export datasets, UI descriptors, and example experiment profiles.
- `runtime-files/`: shared Linux runtime files consumed by both the generic Linux installer and CustoPiZer Raspberry Pi images, including lighttpd config, common systemd web units, logrotate config, tmpfiles config, helper scripts, and `/etc/pioreactor.env`.
- **EXPERIMENTAL** `linux-leader/`: installer scaffold and leader-only service templates for a Debian 13 Linux workstation.

## Release Artifacts

- `release-signing.md`: maintainer and fork instructions for signed `release_<version>.zip` archives, including why release archives are signed and how to recreate the signing setup.

## Boot-partition YAML imports

On Raspberry Pi images, `bootfs_files.service` imports supported YAML files on
each boot after firstboot/everyboot and before the web services and monitor.
Stage files under `/boot/firmware/pioreactor/` (the `pioreactor/` directory when
the boot partition is mounted on another computer):

- `experiment_profiles/*.yaml` or `*.yml`: leader only, using profile schema and semantic validation.
- `models/*.yaml` or `*.yml`: either role, using the `Model` schema.
- `hardware/**/*.yaml` or `*.yml`: either role, preserving nested HAT/model paths. Files must be YAML mappings; layered hardware compatibility is checked by the runtime.

Imports replace matching files under `$DOT_PIOREACTOR` atomically, without
backups, with ownership `pioreactor:www-data`. Successful inputs are removed
from the boot partition. Failed inputs remain with an adjacent `<filename>.log`
and are retried on the next boot. Unsupported files are left untouched. Workers
without `config.ini` defer all imports until their onboarding reboot. Profiles
staged on workers remain untouched. Profiles are made available, never started.

Plugin wheels continue to use the separate `bootfs_plugins.service`. Generic
Linux leaders do not use this Raspberry Pi boot-partition lifecycle. The
upcoming update installs the service for existing images and schedules it for
the next boot.

## Ownership Boundary

The Pioreactor repo owns these files because they describe the Pioreactor application runtime contract. CustoPiZer consumes selected files from here when building Raspberry Pi images, but CustoPiZer still owns Raspberry Pi image-specific boot, hardware, networking, service ordering, and firstboot behavior.

Wi-Fi recovery's script and systemd units live in `runtime-files/bash/pioreactor-wifi-recovery.sh` and `runtime-files/systemd/pioreactor-wifi-recovery.*`. CustoPiZer's asset sync copies them into every Raspberry Pi image build; its common `pioreactor.target` starts the timer. When changing recovery, also bundle matching copies in the next release's update scripts for existing installations. The recovery retries disconnected autoconnect client profiles at most every five minutes, respects intentional disconnects, and retains separate hardware-error checks for SDIO resets.

## WIP Local HTTPS Support

The runtime lighttpd assets include early, disabled support for serving the browser UI over local HTTPS. `runtime-files/lighttpd/10-pioreactor-https.conf` is copied into image and installer inputs, but it is not enabled by default. It expects a generated local certificate bundle at `/etc/pioreactor/tls/local-ui.lighttpd.pem` and proxies `/mqtt` to the existing Mosquitto websocket listener on `127.0.0.1:9001` so an HTTPS-loaded browser can use same-origin WSS.

This is infrastructure for a future opt-in setup flow, not production HTTPS-by-default. Do not change `config.example.ini` to `wss` / `443`, enable the lighttpd HTTPS config, add HTTP-to-HTTPS redirects, or add HSTS until the local CA generation, browser trust onboarding, certificate regeneration, and rollback behavior are productized.
