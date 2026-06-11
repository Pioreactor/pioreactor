#!/bin/bash

set -xeu

export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME=$(hostname)
LEADER_HOSTNAME=$(sudo -u pioreactor -i pio config get cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
  exit 0
fi

LIGHTTPD_CONFIG_SOURCE="$SCRIPT_DIR/50-pioreactorui.conf"
LIGHTTPD_CONFIG_DESTINATION="/etc/lighttpd/conf-available/50-pioreactorui.conf"

if [ ! -s "$LIGHTTPD_CONFIG_SOURCE" ]; then
  sudo -u pioreactor -i pio log -l ERROR -m "Missing or empty Lighttpd update asset: $LIGHTTPD_CONFIG_SOURCE"
  exit 1
fi

LIGHTTPD_CONFIG_TEMP=$(mktemp /etc/lighttpd/conf-available/50-pioreactorui.conf.XXXXXX)
install -o root -g root -m 0644 "$LIGHTTPD_CONFIG_SOURCE" "$LIGHTTPD_CONFIG_TEMP"
mv "$LIGHTTPD_CONFIG_TEMP" "$LIGHTTPD_CONFIG_DESTINATION"

if ! cmp -s "$LIGHTTPD_CONFIG_SOURCE" "$LIGHTTPD_CONFIG_DESTINATION"; then
  sudo -u pioreactor -i pio log -l ERROR -m "Failed to install $LIGHTTPD_CONFIG_DESTINATION"
  exit 1
fi

DATABASE=$(sudo -u pioreactor -i pio config get storage database)

has_legacy_experiment_metadata_columns=$(sudo sqlite3 "$DATABASE" <<'SQL'
SELECT COUNT(*)
FROM pragma_table_info('experiments')
WHERE name IN ('media_used', 'organism_used');
SQL
)

if [ "$has_legacy_experiment_metadata_columns" = "0" ]; then
  exit 0
fi

sudo sqlite3 "$DATABASE" <<'SQL'
PRAGMA busy_timeout = 15000;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA foreign_keys = OFF;
PRAGMA auto_vacuum = INCREMENTAL;

BEGIN TRANSACTION;

INSERT OR IGNORE INTO experiment_tags (
    experiment,
    tag,
    created_at
)
SELECT
    experiment,
    'media: ' || TRIM(media_used),
    created_at
FROM experiments
WHERE media_used IS NOT NULL
  AND TRIM(media_used) != '';

INSERT OR IGNORE INTO experiment_tags (
    experiment,
    tag,
    created_at
)
SELECT
    experiment,
    'organism: ' || TRIM(organism_used),
    created_at
FROM experiments
WHERE organism_used IS NOT NULL
  AND TRIM(organism_used) != '';

DROP VIEW IF EXISTS latest_experiment;
DROP TABLE IF EXISTS experiments_new;

CREATE TABLE experiments_new (
    experiment TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    description TEXT
);

INSERT INTO experiments_new (
    experiment,
    created_at,
    description
)
SELECT
    experiment,
    created_at,
    description
FROM experiments
ORDER BY rowid;

DROP INDEX IF EXISTS experiments_ix;
DROP TABLE experiments;
ALTER TABLE experiments_new RENAME TO experiments;

CREATE UNIQUE INDEX IF NOT EXISTS experiments_ix ON experiments (
    created_at, experiment, description
);

CREATE VIEW IF NOT EXISTS latest_experiment AS
SELECT
    experiment,
    created_at,
    description,
    round((strftime("%s", "now") - strftime("%s", created_at)) / 60 / 60, 0)
        AS delta_hours
FROM experiments
ORDER BY rowid DESC
LIMIT 1;

COMMIT;

PRAGMA foreign_keys = ON;
PRAGMA foreign_key_check;
SQL
