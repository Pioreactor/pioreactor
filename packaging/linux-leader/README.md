# Pioreactor Linux Leader Installer

This directory contains the first scaffold for installing Pioreactor leader-only software on a generic Linux workstation.

Supported first target:

- Debian 13 / Trixie
- systemd
- Python 3.13 from the OS package set
- `amd64` and `arm64`

The installer creates the same core runtime shape as the image path:

- `/home/pioreactor/.pioreactor`
- `/opt/pioreactor/venv`
- `/etc/pioreactor.env`
- `/run/pioreactor`
- `pioreactor.target`
- `pioreactor-leader.target`
- `pioreactor-web.target`

Unlike a Raspberry Pi image, this is leader-only by default. It does not register the workstation as a worker and does not install Raspberry Pi hardware services.

The installer expects to be run from the repository checkout or release archive so it can read:

- `packaging/shared-assets/` for one-time provisioning seed data.
- `packaging/linux-leader/files/` for Linux leader service templates.

These files are intentionally not included in the Python wheel.

## Usage

Install from a local wheel:

```bash
sudo ./install.sh --wheel /path/to/pioreactor-26.4.0-py3-none-any.whl
```

Install from a Pioreactor release tag:

```bash
sudo ./install.sh --version 26.4.0
```

Install from a git ref:

```bash
sudo ./install.sh --git-ref develop
```

Optional flags:

```bash
--leader-hostname HOSTNAME
--leader-address ADDRESS
--ui-port PORT
```

The installer preserves an existing `/home/pioreactor/.pioreactor/config.ini` and database. It only initializes missing files.

## Current Limits

- This is not a `.deb` yet.
- Default Mosquitto credentials still match the image defaults unless overridden by environment variable.
- Worker onboarding docs still need to be added.
- The installer has not yet been validated on fresh Debian 13 amd64/arm64 machines.
