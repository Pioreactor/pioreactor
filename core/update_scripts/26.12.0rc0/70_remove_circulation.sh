#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR="/home/pioreactor/.pioreactor"

# Remove only the retired built-in descriptors, on leaders and workers.
rm -f "$DOT_PIOREACTOR/ui/jobs/14_circulate_media.yaml" \
      "$DOT_PIOREACTOR/ui/jobs/15_circulate_alt_media.yaml"
