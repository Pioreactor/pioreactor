# Packaging

This directory contains files used to build or install Pioreactor outside the normal Python package runtime. Most files here are provisioning inputs: they seed databases, config directories, system services, or image-builder workspaces.

## Directories

- `shared-assets/`: one-time provisioning seed data shared by Linux leader installs and CustoPiZer image builds, including SQL, config, export datasets, UI descriptors, and example experiment profiles.
- **EXPERIMENTAL** `linux-leader/`: installer scaffold and service templates for a leader-only Debian 13 Linux workstation.

## Ownership Boundary

The Pioreactor repo owns these files because they describe the Pioreactor application runtime contract. CustoPiZer consumes selected files from here when building Raspberry Pi images, but CustoPiZer still owns Raspberry Pi image-specific boot, hardware, networking, and firstboot behavior.
