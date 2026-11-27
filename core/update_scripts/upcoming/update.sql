PRAGMA foreign_keys = ON;

-- Replay 26.9.0 for standalone databases that were dormant while joined.
CREATE TABLE IF NOT EXISTS experiment_chart_preferences (
    experiment TEXT NOT NULL PRIMARY KEY,
    overview_chart_keys TEXT,
    pioreactor_chart_keys TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

-- Replay 26.13.0 for joined leader-workers whose 26.12.0 updater skipped its SQL.

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
