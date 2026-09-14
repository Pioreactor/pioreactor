#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_ROOT="${1:-/home/pioreactor/.pioreactor/hardware/models}"
test -s "$SCRIPT_DIR/od.yaml"

for model in pioreactor_20ml/1.0 pioreactor_20ml/1.1 pioreactor_20ml/1.5 \
    pioreactor_40ml/1.0 pioreactor_40ml/1.5 pioreactor_20ml_XR/1.5 pioreactor_40ml_XR/1.5; do
    destination="$MODEL_ROOT/$model/od.yaml"
    if [ -e "$destination" ]; then
        continue
    fi
    install -d -o pioreactor -g www-data -m 0755 "$MODEL_ROOT/$model"
    tmp=$(mktemp "$MODEL_ROOT/$model/.od.yaml.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    install -o pioreactor -g www-data -m 0644 "$SCRIPT_DIR/od.yaml" "$tmp"
    mv "$tmp" "$destination"
    test -s "$destination"
done
