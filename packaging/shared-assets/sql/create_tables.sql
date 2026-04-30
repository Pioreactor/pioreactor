CREATE TABLE IF NOT EXISTS od_readings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL NOT NULL,
    angle INTEGER NOT NULL,
    channel INTEGER CHECK (channel IN (1, 2, 3, 4)) NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS od_readings_ix
ON od_readings (experiment, pioreactor_unit, channel, timestamp);

CREATE TABLE IF NOT EXISTS raw_od_readings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL NOT NULL,
    channel INTEGER CHECK (channel IN (1, 2, 3, 4)) NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS raw_od_readings_ix
ON raw_od_readings (experiment, pioreactor_unit, channel, timestamp);


CREATE TABLE IF NOT EXISTS experiment_tags (
    experiment TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (experiment, tag),
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS experiment_tags_experiment_created_at_tag_ix
ON experiment_tags (experiment, created_at, tag);


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



CREATE TABLE IF NOT EXISTS alt_media_fractions (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    alt_media_fraction REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS alt_media_fractions_ix
ON alt_media_fractions (experiment);


CREATE TABLE IF NOT EXISTS liquid_volumes (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    liquid_volume REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS liquid_volumes_ix
ON liquid_volumes (experiment);



CREATE TABLE IF NOT EXISTS od_readings_filtered (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    normalized_od_reading REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS od_readings_filtered_ix
ON od_readings_filtered (experiment, pioreactor_unit, timestamp);



CREATE TABLE IF NOT EXISTS dosing_events (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    volume_change_ml REAL NOT NULL,
    source_of_event TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS led_change_events (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    channel TEXT CHECK (channel IN ('A', 'B', 'C', 'D')) NOT NULL,
    intensity REAL NOT NULL,
    source_of_event TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS dosing_events_ix
ON dosing_events (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS led_change_events_ix
ON led_change_events (experiment, pioreactor_unit);




CREATE TABLE IF NOT EXISTS growth_rates (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    rate REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS growth_rates_ix
ON growth_rates (experiment, pioreactor_unit, timestamp);



CREATE TABLE IF NOT EXISTS logs (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    level TEXT,
    task TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS logs_exp_timestamp_ix
    ON logs (experiment, timestamp DESC);

CREATE INDEX IF NOT EXISTS logs_unit_timestamp_ix
   ON logs (pioreactor_unit, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_logs_level_timestamp_desc
    ON logs (level, timestamp DESC);

CREATE TABLE IF NOT EXISTS experiments (
    experiment TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    description TEXT,
    media_used TEXT,
    organism_used TEXT
);

-- since we are almost always calling this like "SELECT * FROM experiments ORDER BY created_at DESC LIMIT 1",
-- a index on all columns is much faster, BigO(n). This table is critical for the entire webpage performance.
-- not the order of the values in the index is important to get this performance.
-- https://medium.com/@JasonWyatt/squeezing-performance-from-sqlite-indexes-indexes-c4e175f3c346
-- Later: but why description??
CREATE UNIQUE INDEX IF NOT EXISTS experiments_ix ON experiments (
    created_at, experiment, description
);

-- the latest experiment is defined as the on that is most recently inserted into the database. Why not use created_at?
-- it's possible that an experiment can be created_at ORDER != rowid order if users are playing with the times (or using local access point)
CREATE VIEW IF NOT EXISTS latest_experiment AS
SELECT
    experiment,
    created_at,
    description,
    media_used,
    organism_used,
    round((strftime("%s", "now") - strftime("%s", created_at)) / 60 / 60, 0)
        AS delta_hours
FROM experiments
ORDER BY rowid DESC
LIMIT 1;


CREATE TABLE IF NOT EXISTS dosing_automation_settings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    automation_name TEXT NOT NULL,
    settings BLOB NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS led_automation_settings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    automation_name TEXT NOT NULL,
    settings BLOB NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS temperature_automation_settings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    automation_name TEXT NOT NULL,
    settings BLOB NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS temperature_automation_settings_ix
ON temperature_automation_settings (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS dosing_automation_settings_ix
ON dosing_automation_settings (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS led_automation_settings_ix
ON led_automation_settings (experiment, pioreactor_unit);


CREATE TABLE IF NOT EXISTS kalman_filter_outputs (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    state_0 REAL NOT NULL,
    state_1 REAL NOT NULL,
    state_2 REAL NOT NULL,
    cov_00 REAL NOT NULL,
    cov_01 REAL NOT NULL,
    cov_02 REAL NOT NULL,
    cov_11 REAL NOT NULL,
    cov_12 REAL NOT NULL,
    cov_22 REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS temperature_readings (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    temperature_c REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS temperature_readings_ix
ON temperature_readings (experiment, pioreactor_unit, timestamp);



CREATE TABLE IF NOT EXISTS stirring_rates (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    measured_rpm REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS stirring_rates_ix
ON stirring_rates (experiment, pioreactor_unit);


CREATE TABLE IF NOT EXISTS config_files_histories (
    timestamp TEXT NOT NULL,
    filename TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS config_files_histories_ix
ON config_files_histories (filename);


CREATE TABLE IF NOT EXISTS od_blanks (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    channel TEXT CHECK (channel IN ('1', '2')) NOT NULL,
    angle INTEGER NOT NULL,
    od_reading REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS ir_led_intensities (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    relative_intensity REAL NOT NULL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);



CREATE INDEX IF NOT EXISTS ir_led_intensities_ix
ON ir_led_intensities (experiment, pioreactor_unit);


CREATE TABLE IF NOT EXISTS pioreactor_unit_labels (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (pioreactor_unit, experiment),
    UNIQUE (label, experiment),
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS pioreactor_unit_labels_ix
ON pioreactor_unit_labels (experiment, pioreactor_unit);


CREATE TABLE IF NOT EXISTS temperature_automation_events (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_name TEXT NOT NULL,
    message TEXT,
    data TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dosing_automation_events (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_name TEXT NOT NULL,
    message TEXT,
    data TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS led_automation_events (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_name TEXT NOT NULL,
    message TEXT,
    data TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS temperature_automation_events_ix
ON temperature_automation_events (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS dosing_automation_events_ix
ON dosing_automation_events (experiment, pioreactor_unit);

CREATE INDEX IF NOT EXISTS led_automation_events_ix
ON led_automation_events (experiment, pioreactor_unit);



CREATE TABLE IF NOT EXISTS pioreactor_unit_activity_data (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    od_reading REAL,
    od_fused REAL,
    normalized_od_reading REAL,
    temperature_c REAL,
    growth_rate REAL,
    measured_rpm REAL,
    led_a_intensity_update REAL,
    led_b_intensity_update REAL,
    led_c_intensity_update REAL,
    led_d_intensity_update REAL,
    add_media_ml REAL,
    remove_waste_ml REAL,
    add_alt_media_ml REAL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


-- heads up: we need this specific index for to handle ON CONFLICT statements in the triggers. Don't change it.
CREATE UNIQUE INDEX IF NOT EXISTS pioreactor_unit_activity_data_ix
ON pioreactor_unit_activity_data (experiment, pioreactor_unit, timestamp);

-- a rollup of the pioreactor_unit_activity_data to the minute
CREATE VIEW IF NOT EXISTS pioreactor_unit_activity_data_rollup AS
SELECT
    experiment,
    pioreactor_unit,
    datetime(strftime('%Y-%m-%dT%H:%M:00', timestamp)) AS timestamp,
    avg(od_reading) AS avg_od_reading,
    avg(od_fused) AS avg_od_fused,
    avg(normalized_od_reading) AS avg_normalized_od_reading,
    avg(temperature_c) AS avg_temperature_c,
    avg(growth_rate) AS avg_growth_rate,
    avg(measured_rpm) AS avg_measured_rpm,
    sum(add_media_ml) AS sum_add_media_ml,
    sum(remove_waste_ml) AS sum_remove_waste_ml,
    sum(add_alt_media_ml) AS sum_add_alt_media_ml
FROM pioreactor_unit_activity_data
GROUP BY experiment, pioreactor_unit, datetime(strftime('%Y-%m-%dT%H:%M:00', timestamp));


CREATE TABLE IF NOT EXISTS calibrations (
    pioreactor_unit TEXT NOT NULL,
    created_at TEXT NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    name TEXT NOT NULL,
    is_current INTEGER DEFAULT 0 NOT NULL,
    set_to_current_at TEXT,
    UNIQUE (pioreactor_unit, type, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS calibrations_ix
ON calibrations (pioreactor_unit, type, name);


CREATE TABLE IF NOT EXISTS pwm_dcs (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    channel_1 REAL,
    channel_2 REAL,
    channel_3 REAL,
    channel_4 REAL,
    channel_5 REAL,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS pwm_dcs_ix
ON pwm_dcs (experiment, pioreactor_unit);



CREATE TABLE IF NOT EXISTS experiment_profile_runs (
    started_at TEXT NOT NULL,
    experiment_profile_name TEXT NOT NULL,
    experiment TEXT,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);


--
-- the tables below are more "oltp" than "olap", hence the FK
--

CREATE TABLE IF NOT EXISTS experiment_worker_assignments (
    pioreactor_unit TEXT NOT NULL,
    experiment TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    -- force a worker to only ever be assigned to a single experiment.
    UNIQUE (pioreactor_unit),
    FOREIGN KEY (pioreactor_unit) REFERENCES workers (
        pioreactor_unit
    ) ON DELETE CASCADE,
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workers (
    pioreactor_unit TEXT NOT NULL, -- id
    added_at TEXT NOT NULL,
    model_name TEXT,
    model_version TEXT,
    is_active INTEGER DEFAULT 1 NOT NULL,
    UNIQUE (pioreactor_unit)
);


-- see triggers for how this is populated!
CREATE TABLE IF NOT EXISTS experiment_worker_assignments_history (
    pioreactor_unit TEXT NOT NULL,
    experiment TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    unassigned_at TEXT,
    UNIQUE (pioreactor_unit, experiment, assigned_at)
);

CREATE INDEX IF NOT EXISTS experiment_worker_assignments_history_ix
    ON experiment_worker_assignments_history (
        experiment,
        pioreactor_unit,
        assigned_at,
        unassigned_at
    );
