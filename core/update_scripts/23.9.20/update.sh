#!/bin/bash

set -x
set -e

export LC_ALL=C

# this is a duplicate of 23.9.19

wget -O /usr/local/bin/install_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/1d95fa4952398aab1dda09f8cc6d79a8e72197d4/workspace/scripts/files/bash/install_pioreactor_plugin.sh
sudo chown pioreactor:pioreactor /home/pioreactor/.pioreactor/experiment_profiles/demo_stirring_example.yaml || true
