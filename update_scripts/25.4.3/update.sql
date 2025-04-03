PRAGMA busy_timeout = 15000;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;

ALTER TABLE workers ADD COLUMN model_version TEXT;
ALTER TABLE workers ADD COLUMN model_name TEXT;

CREATE TABLE IF NOT EXISTS raw_od_readings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL NOT NULL,
    channel INTEGER CHECK (channel IN (1, 2)) NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS raw_od_readings_ix
ON od_readings (experiment, pioreactor_unit, timestamp);
