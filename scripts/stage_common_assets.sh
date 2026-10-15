#!/bin/bash
# Build the same flat, inspectable payload for release updates and image builds.
set -euo pipefail
export LC_ALL=C

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DESTINATION=${1:?Usage: stage_common_assets.sh OUTPUT_DIRECTORY}
SHARED="$REPO_ROOT/packaging/shared-assets"
RUNTIME="$REPO_ROOT/packaging/runtime-files"
mkdir -p "$DESTINATION"
MANIFEST="$DESTINATION/common-assets.tsv"
: > "$MANIFEST"

stage() {
    local source=$1 destination=$2 owner=$3 group=$4 mode=$5 asset
    asset="common_$(printf '%s' "$destination" | tr / _)"
    # Templates are installed as data, never interpreted by the release updater.
    asset="$asset.asset"
    cp "$source" "$DESTINATION/$asset"
    printf '%s\t%s\t%s\t%s\t%s\n' "$asset" "$destination" "$owner" "$group" "$mode" >> "$MANIFEST"
}

for tree in ui exportable_datasets experiment_profiles camera; do
    while IFS= read -r source; do
        relative=${source#"$SHARED/pioreactor/"}
        stage "$source" "/home/pioreactor/.pioreactor/$relative" pioreactor www-data 0664
    done < <(find "$SHARED/pioreactor/$tree" -type f ! -name .DS_Store ! -name README.md | sort)
done

# A missing model YAML can intentionally disable a hardware module. Keep the
# upgrade copy inactive; image provisioning seeds a fresh hardware tree separately.
while IFS= read -r source; do
    relative=${source#"$SHARED/pioreactor/hardware/"}
    stage "$source" "/usr/share/pioreactor/provisioning/hardware/$relative" root root 0644
done < <(find "$SHARED/pioreactor/hardware" -type f ! -name .DS_Store | sort)

for source in "$SHARED/sql/"*.sql; do
    stage "$source" "/usr/share/pioreactor/provisioning/sql/$(basename "$source")" root root 0644
done
stage "$SHARED/pioreactor/config.example.ini" /usr/share/pioreactor/provisioning/config.example.ini root root 0644
for unit in avahi_aliases.service backup-database.service backup-database.timer pioreactor-leader.target ui-exports-cleanup.service ui-exports-cleanup.timer; do
    source="$RUNTIME/systemd/$unit"
    stage "$source" "/usr/share/pioreactor/provisioning/systemd/$(basename "$source")" root root 0644
done
stage "$RUNTIME/bash/avahi_aliases.sh" /usr/share/pioreactor/provisioning/bash/avahi_aliases.sh root root 0755
stage "$REPO_ROOT/packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh" /usr/local/bin/add_new_pioreactor_worker_from_leader.sh root root 0755
cp "$REPO_ROOT/packaging/runtime-files/bash/install_common_assets.sh" "$DESTINATION/install_common_assets.sh"
