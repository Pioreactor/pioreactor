#!/bin/bash

set -x
set -e

export LC_ALL=C

rm -f /home/pioreactor/.pioreactor/experiment_profiles/demo_stirring_example.yaml

cat <<EOT >> /home/pioreactor/.pioreactor/experiment_profiles/demo_stirring_example.yaml
experiment_profile_name: demo_stirring_example

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile to start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 400.0
        - type: update
          hours_elapsed: 0.025
          options:
            target_rpm: 800.0
        - type: stop
          hours_elapsed: 0.05
EOT
