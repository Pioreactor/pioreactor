#!/bin/bash

set -x
set -e

export LC_ALL=C

# Get the Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')

# Check if the version is 3.11
if [[ "$python_version" != "3.11"* ]]; then
    echo "Error: Required Python version 3.11 not found."
    exit 1
fi
