#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)
if [ "$(hostname)" != "$LEADER_HOSTNAME" ]; then
  exit 0
fi

DATABASE=$(sudo -u pioreactor -i pio config get storage database)
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python "$SCRIPT_DIR/migrate_experiment_started_at.py" "$DATABASE"

# Update descriptor metadata without reserializing YAML or replacing customizations.
sudo -u pioreactor -i /opt/pioreactor/venv/bin/python <<'PY'
from pioreactor.paths import get_dot_pioreactor_path

root = get_dot_pioreactor_path()
for directory in (root / "exportable_datasets", root / "plugins" / "exportable_datasets"):
    for path in directory.glob("*.y*ml"):
        original = path.read_text(encoding="utf-8")
        updated = original.replace("hours_since_experiment_created", "hours_since_experiment_started")
        updated = updated.replace("Hours from experiment creation to", "Hours from experiment start to")
        if updated != original:
            path.write_text(updated, encoding="utf-8")
PY
