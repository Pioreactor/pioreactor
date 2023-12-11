#!/bin/bash

set -x
set -e

export LC_ALL=C

# Get the directory where the script is located
SCRIPT_DIR=$(dirname "$0")

# Copy update_ui.sh from the script's directory
sudo cp "${SCRIPT_DIR}/update_ui.sh" /usr/local/bin/
