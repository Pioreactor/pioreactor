# create_tables.sql

CREATE TABLE IF NOT EXISTS od_readings_raw (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    od_reading_v           REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    angle                  TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS od_readings_raw_ix
ON od_readings_raw (experiment, morbidostat_unit, angle);



CREATE TABLE IF NOT EXISTS alt_media_fraction (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    alt_media_fraction     REAL  NOT NULL,
    experiment             TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS alt_media_fraction_ix
ON alt_media_fraction (experiment, morbidostat_unit);


CREATE TABLE IF NOT EXISTS fluoresence_readings_raw (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    fluoresence_reading_v  REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    ex_nm                  REAL  NOT NULL,
    em_nm                  REAL  NOT NULL
);

CREATE INDEX IF NOT EXISTS fluoresence_readings_raw_ix
ON fluoresence_readings_raw (experiment, morbidostat_unit);

CREATE TABLE IF NOT EXISTS od_readings_filtered (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    od_reading_v           REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    angle                  TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS od_readings_filtered_ix
ON od_readings_filtered (experiment, morbidostat_unit, angle);


CREATE TABLE IF NOT EXISTS io_events (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    event                  TEXT  NOT NULL,
    volume_change_ml       REAL  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS io_events_ix
ON io_events (experiment);



CREATE TABLE IF NOT EXISTS growth_rates (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    rate                   REAL  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS growth_rates_ix
ON growth_rates (experiment, morbidostat_unit);



CREATE TABLE IF NOT EXISTS logs (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    message                TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS logs_ix
ON logs (experiment, morbidostat_unit);


CREATE TABLE IF NOT EXISTS experiments (
    experiment             TEXT  NOT NULL UNIQUE,
    timestamp              TEXT  NOT NULL,
    description            TEXT
);

CREATE INDEX IF NOT EXISTS experiments_ix
ON experiments (experiment);


CREATE TABLE IF NOT EXISTS pid_logs (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
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

CREATE INDEX IF NOT EXISTS pid_logs_ix
ON pid_logs (experiment);
