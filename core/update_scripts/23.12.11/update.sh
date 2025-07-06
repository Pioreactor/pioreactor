#!/bin/bash

set -x

export LC_ALL=C

# Get the directory where the script is located
SCRIPT_DIR=$(dirname "$0")

# Attempt to download update_ui.sh
if ! wget -O "${SCRIPT_DIR}/update_ui.sh" https://github.com/Pioreactor/pioreactor/releases/download/23.12.11/update_ui.sh; then
    echo "Failed to download update_ui.sh"
fi

# Ensure the script is executable
chmod +x "${SCRIPT_DIR}/update_ui.sh"

# Copy update_ui.sh from the script's directory
sudo cp "${SCRIPT_DIR}/update_ui.sh" /usr/local/bin/
