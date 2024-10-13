#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HUEY_SERVICE_FILE="/etc/systemd/system/huey.service"

mv "$SCRIPT_DIR"/huey.service $HUEY_SERVICE_FILE

# Reload systemd to apply changes
sudo systemctl daemon-reload
sudo systemctl restart huey.service

sudo chown pioreactor:www-data /var/www/pioreactorui/__pycache__ || :
sudo chown pioreactor:www-data /var/www/pioreactorui/pioreactorui/__pycache__ || :

# new table definitions in local metadata sqlite3

# Path to the SQLite3 database
DATABASE="/tmp/local_intermittent_pioreactor_metadata.sqlite"

# Rename column 'name' to 'job_name' in 'pio_job_metadata' table
sqlite3 "$DATABASE" <<EOF || true
PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

ALTER TABLE pio_job_metadata RENAME COLUMN name TO job_name;

ALTER TABLE pio_job_metadata ADD COLUMN is_long_running_job INTEGER NOT NULL DEFAULT 0;

COMMIT;

PRAGMA foreign_keys=on;
EOF

echo "Schema changes applied successfully."
