CREATE TABLE IF NOT EXISTS od_readings_raw (
    timestamp              TEXT     NOT NULL,
    pioreactor_unit        TEXT     NOT NULL,
    od_reading_v           REAL     NOT NULL,
    experiment             TEXT     NOT NULL,
    angle                  TEXT     NOT NULL,
    channel                INTEGER  NOT NULL
);

CREATE INDEX IF NOT EXISTS od_readings_raw_ix
ON od_readings_raw (experiment);



CREATE TABLE IF NOT EXISTS alt_media_fraction (
    timestamp              TEXT  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL,
    alt_media_fraction     REAL  NOT NULL,
    experiment             TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS alt_media_fraction_ix
ON alt_media_fraction (experiment);



CREATE TABLE IF NOT EXISTS od_readings_filtered (
    timestamp              TEXT     NOT NULL,
    pioreactor_unit        TEXT     NOT NULL,
    normalized_od_reading  REAL     NOT NULL,
    experiment             TEXT     NOT NULL,
    angle                  TEXT     NOT NULL,
    channel                INTEGER  NOT NULL
);

CREATE INDEX IF NOT EXISTS od_readings_filtered_ix
ON od_readings_filtered (experiment);



CREATE TABLE IF NOT EXISTS dosing_events (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    event                  TEXT  NOT NULL,
    volume_change_ml       REAL  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL,
    source_of_event        TEXT
);



CREATE TABLE IF NOT EXISTS led_events (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    event                  TEXT  NOT NULL,
    channel                TEXT  NOT NULL,
    intensity              REAL  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL,
    source_of_event        TEXT
);



CREATE TABLE IF NOT EXISTS growth_rates (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    rate                   REAL  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS growth_rates_ix
ON growth_rates (experiment);



CREATE TABLE IF NOT EXISTS logs (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    message                TEXT  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL,
    source                 TEXT  NOT NULL,
    level                  TEXT,
    task                   TEXT
);

CREATE INDEX IF NOT EXISTS logs_ix
ON logs (experiment, level);



CREATE TABLE IF NOT EXISTS experiments (
    experiment             TEXT  NOT NULL UNIQUE,
    timestamp              TEXT  NOT NULL,
    description            TEXT
);

-- since we are almost always calling this like "SELECT * FROM experiments ORDER BY timestamp DESC LIMIT 1",
-- a index on all columns is much faster, BigO(n). This table is critical for the entire webpage performance.
-- not the order of the values in the index is important to get this performance.
-- https://medium.com/@JasonWyatt/squeezing-performance-from-sqlite-indexes-indexes-c4e175f3c346
CREATE INDEX IF NOT EXISTS experiments_ix ON experiments (timestamp, experiment, description);



CREATE TABLE IF NOT EXISTS pid_logs (
    timestamp              TEXT  NOT NULL,
    pioreactor_unit        TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    job_name               TEXT  NOT NULL,
    target_name            TEXT  NOT NULL,
    setpoint               REAL  NOT NULL,
    output_limits_lb       REAL,
    output_limits_ub       REAL,
    Kd                     REAL  NOT NULL,
    Ki                     REAL  NOT NULL,
    Kp                     REAL  NOT NULL,
    integral               REAL,
    proportional           REAL,
    derivative             REAL,
    latest_input           REAL  NOT NULL,
    latest_output          REAL  NOT NULL
);



CREATE TABLE IF NOT EXISTS dosing_automation_settings (
    pioreactor_unit          TEXT  NOT NULL,
    experiment               TEXT  NOT NULL,
    started_at               TEXT  NOT NULL,
    ended_at                 TEXT,
    automation               TEXT  NOT NULL,
    settings                 TEXT  NOT NULL
);



CREATE TABLE IF NOT EXISTS led_automation_settings (
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    started_at               TEXT NOT NULL,
    ended_at                 TEXT,
    automation               TEXT NOT NULL,
    settings                 TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS temperature_automation_settings (
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    started_at               TEXT NOT NULL,
    ended_at                 TEXT,
    automation               TEXT NOT NULL,
    settings                 TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS kalman_filter_outputs (
    timestamp                TEXT NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    state                    TEXT NOT NULL,
    covariance_matrix        TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS temperature_readings (
    timestamp                TEXT  NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    temperature_c            REAL NOT NULL
);


CREATE INDEX IF NOT EXISTS temperature_readings_ix
ON temperature_readings (experiment);



CREATE TABLE IF NOT EXISTS stirring_rates (
    timestamp                TEXT NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    rpm                      REAL NOT NULL
);



CREATE TABLE IF NOT EXISTS od_reading_statistics (
    timestamp                TEXT NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    source                   TEXT NOT NULL,
    estimator                TEXT NOT NULL,
    estimate                 REAL NOT NULL
);
