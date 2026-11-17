PRAGMA foreign_keys = ON;

-- Limit media-rate calculations to the recent dosing window.
CREATE INDEX IF NOT EXISTS dosing_events_exp_timestamp_ix
ON dosing_events (experiment, timestamp);

CREATE TABLE IF NOT EXISTS experiment_unit_colors (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    color TEXT NOT NULL,
    PRIMARY KEY (experiment, pioreactor_unit),
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

-- Chart queries seek by (experiment, pioreactor_unit, channel, timestamp). Databases created before
-- `channel` joined these indexes kept the old three-column definition (and 25.4.3 put
-- raw_od_readings_ix on the wrong table), so rebuild both to match create_tables.sql.
DROP INDEX IF EXISTS od_readings_ix;
CREATE INDEX od_readings_ix
ON od_readings (experiment, pioreactor_unit, channel, timestamp);

DROP INDEX IF EXISTS raw_od_readings_ix;
CREATE INDEX raw_od_readings_ix
ON raw_od_readings (experiment, pioreactor_unit, channel, timestamp);
