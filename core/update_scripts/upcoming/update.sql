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
