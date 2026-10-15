#!/bin/bash
# Install missing common assets without changing role, services or user files.
set -euo pipefail
export LC_ALL=C

ASSETS=${1:?Usage: install_common_assets.sh ASSET_DIRECTORY [DESTINATION_ROOT]}
DESTINATION_ROOT=${2:-}
MANIFEST="$ASSETS/common-assets.tsv"
if [ ! -f "$MANIFEST" ] || [ ! -s "$MANIFEST" ]; then
    echo "Missing or empty common asset manifest: $MANIFEST" >&2
    exit 1
fi

# Validate the entire payload before writing any destination.
while IFS=$'\t' read -r asset destination owner group mode; do
    if [ ! -f "$ASSETS/$asset" ] || [ ! -s "$ASSETS/$asset" ]; then
        echo "Missing or empty common asset: $ASSETS/$asset" >&2
        exit 1
    fi
done < "$MANIFEST"

ensure_directory() {
    local directory=$1 owner=$2 group=$3 mode=$4
    if [ ! -d "$directory" ]; then
        ensure_directory "$(dirname "$directory")" "$owner" "$group" "$mode"
        install -d -o "$owner" -g "$group" -m "$mode" "$directory"
    fi
}

temporary=
trap 'if [ -n "$temporary" ]; then rm -f "$temporary"; fi' EXIT
while IFS=$'\t' read -r asset destination owner group mode; do
    destination="$DESTINATION_ROOT$destination"
    # Existing defaults may have been customized; dangling symlinks also belong to the user.
    if [ -e "$destination" ] || [ -L "$destination" ]; then
        continue
    fi
    directory=$(dirname "$destination")
    if [ "$owner" = pioreactor ]; then
        directory_mode=2775
    else
        directory_mode=0755
    fi
    ensure_directory "$directory" "$owner" "$group" "$directory_mode"
    temporary=$(mktemp "$directory/.common-assets.XXXXXX")
    install -o "$owner" -g "$group" -m "$mode" "$ASSETS/$asset" "$temporary"
    mv "$temporary" "$destination"
    temporary=
    cmp "$ASSETS/$asset" "$destination"
done < "$MANIFEST"

for directory in ui/charts exportable_datasets; do
    destination="$DESTINATION_ROOT/home/pioreactor/.pioreactor/plugins/$directory"
    ensure_directory "$destination" pioreactor www-data 2775
done
