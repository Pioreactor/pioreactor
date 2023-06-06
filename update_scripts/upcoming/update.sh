#!/bin/bash

set -x
set -e

export LC_ALL=C



sudo mkdir /home/pioreactor/.pioreactor/experiment_profiles/
sudo chown pioreactor:pioreactor /home/pioreactor/.pioreactor/experiment_profiles/


cat <<EOT >> /home/pioreactor/.pioreactor/experiment_profiles/demo_stirring_example.yaml
experiment_profile_name: demo_stirring_example

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile to start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  stirring:
    actions:
      - type: start
        hours_elapsed: 0.0
        parameters:
          target_rpm: 400.0
      - type: update
        hours_elapsed: 0.025
        options:
          target_rpm: 800.0
      - type: stop
        hours_elapsed: 0.05
EOT


cat <<EOT >> /home/pioreactor/.pioreactor/experiment_profiles/complex_example.yaml
experiment_profile_name: complex_example

metadata:
  author: Cam Davidson-Pilon
  description: A more complex profile to start stirring, heating, and (later) od_reading and growth_rate_calculating.

common:
  stirring:
    actions:
      - type: start
        hours_elapsed: 0.0
        parameters:
          target_rpm: 400.0
  temperature_control:
    actions:
      - type: start
        hours_elapsed: 0.0
        options:
          automation_name: thermostat
          target_temperature: 30
  od_reading:
    actions:
      - type: start
        hours_elapsed: 0.25
  growth_rate_calculating:
    actions:
      - type: start
        hours_elapsed: 0.33
EOT


wget -O /usr/local/bin/install_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/install_pioreactor_plugin.sh
wget -O /usr/local/bin/uninstall_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/uninstall_pioreactor_plugin.sh
