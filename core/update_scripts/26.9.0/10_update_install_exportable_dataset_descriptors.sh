#!/bin/bash

set -xeu

export LC_ALL=C

DOT_PIOREACTOR=/home/pioreactor/.pioreactor
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
EXPORTABLE_DATASETS_DIR="$DOT_PIOREACTOR/exportable_datasets"
tmp=""

clean_up() {
    if [ -n "$tmp" ]; then
        rm -f "$tmp"
    fi
}

trap clean_up EXIT

require_descriptor_asset() {
    local path="$1"
    local dataset_name="$2"

    [ -f "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Missing exportable dataset descriptor update asset: $path"
        exit 1
    }
    [ -s "$path" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Empty exportable dataset descriptor update asset: $path"
        exit 1
    }
    grep -q "^dataset_name: $dataset_name$" "$path" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Exportable dataset descriptor has wrong dataset_name: $path"
        exit 1
    }
    grep -q "^has_experiment: true$" "$path" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Exportable dataset descriptor is not experiment-scoped: $path"
        exit 1
    }
}

install_descriptor() {
    local filename="$1"
    local dataset_name="$2"
    local src="$SCRIPT_DIR/$filename"
    local dst="$EXPORTABLE_DATASETS_DIR/$filename"

    require_descriptor_asset "$src" "$dataset_name"

    install -d -o pioreactor -g www-data -m 2775 "$EXPORTABLE_DATASETS_DIR"
    tmp="$(mktemp "$EXPORTABLE_DATASETS_DIR/.${filename}.XXXXXX")"
    install -o pioreactor -g www-data -m 0664 "$src" "$tmp"
    mv "$tmp" "$dst"
    tmp=""

    [ -s "$dst" ] || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is empty"
        exit 1
    }
    grep -q "^dataset_name: $dataset_name$" "$dst" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst has wrong dataset_name"
        exit 1
    }
    grep -q "^has_experiment: true$" "$dst" || {
        sudo -u pioreactor -i pio log -l ERROR -m "Install postcondition failed: $dst is not experiment-scoped"
        exit 1
    }
}

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    exit 0
fi

install_descriptor 04_experiments.yaml experiments
install_descriptor 04_experiment_tags.yaml experiment_tags
