PRAGMA busy_timeout = 15000;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;

CREATE TABLE IF NOT EXISTS od_readings_fused (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS od_readings_fused_ix
ON od_readings_fused (experiment, pioreactor_unit, timestamp);
