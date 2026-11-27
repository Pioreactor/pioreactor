#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Plugin installs used `pip install --ignore-installed`, which could leave newer copies of pinned
# dependencies (e.g. Adafruit-Blinka 10) written over the installed ones. Restore them from the
# bundled wheels before this release's wheel installs.
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python "$SCRIPT_DIR/repair_duplicate_python_packages.py" "$SCRIPT_DIR/wheels"
