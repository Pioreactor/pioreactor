# Packaging

This directory contains files used to build or install Pioreactor outside the normal Python package runtime. Most files here are provisioning inputs: they seed databases, config directories, system services, or image-builder workspaces.

## Directories

- `shared-assets/`: one-time provisioning seed data shared by Linux installs and CustoPiZer image builds, including SQL, config, export datasets, UI descriptors, and example experiment profiles.
- `runtime-files/`: shared Linux runtime files consumed by both the generic Linux installer and CustoPiZer Raspberry Pi images, including lighttpd config, common systemd web units, logrotate config, tmpfiles config, helper scripts, and `/etc/pioreactor.env`.
- **EXPERIMENTAL** `linux-leader/`: installer scaffold and leader-only service templates for a Debian 13 Linux workstation.

## Release Artifacts

- `release-signing.md`: maintainer and fork instructions for signed `release_<version>.zip` archives, including why release archives are signed and how to recreate the signing setup.

## Ownership Boundary

The Pioreactor repo owns these files because they describe the Pioreactor application runtime contract. CustoPiZer consumes selected files from here when building Raspberry Pi images, but CustoPiZer still owns Raspberry Pi image-specific boot, hardware, networking, service ordering, and firstboot behavior.

## WIP Local HTTPS Support

The runtime lighttpd assets include early, disabled support for serving the browser UI over local HTTPS. `runtime-files/lighttpd/10-pioreactor-https.conf` is copied into image and installer inputs, but it is not enabled by default. It expects a generated local certificate bundle at `/etc/pioreactor/tls/local-ui.lighttpd.pem` and proxies `/mqtt` to the existing Mosquitto websocket listener on `127.0.0.1:9001` so an HTTPS-loaded browser can use same-origin WSS.

This is infrastructure for a future opt-in setup flow, not production HTTPS-by-default. Do not change `config.example.ini` to `wss` / `443`, enable the lighttpd HTTPS config, add HTTP-to-HTTPS redirects, or add HSTS until the local CA generation, browser trust onboarding, certificate regeneration, and rollback behavior are productized.
