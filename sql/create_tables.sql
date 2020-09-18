# create_tables.sql

CREATE TABLE IF NOT EXISTS od_readings_raw (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    od_reading_v           REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    angle                  TEXT  NOT NULL
);


CREATE TABLE IF NOT EXISTS fluoresence_readings_raw (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    fluoresence_reading_v  REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    ex_nm                  REAL  NOT NULL
    em_nm                  REAL  NOT NULL
);


CREATE TABLE IF NOT EXISTS od_readings_filtered (
    timestamp              TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL,
    od_reading_v           REAL  NOT NULL,
    experiment             TEXT  NOT NULL,
    angle                  TEXT  NOT NULL
);

CREATE TABLE IF NOT EXISTS io_events (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    event                  TEXT  NOT NULL,
    volume_change_ml       REAL  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);

CREATE TABLE IF NOT EXISTS growth_rates (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    rate                   REAL  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    timestamp              TEXT  NOT NULL,
    experiment             TEXT  NOT NULL,
    message                TEXT  NOT NULL,
    morbidostat_unit       TEXT  NOT NULL
);


CREATE TABLE IF NOT EXISTS experiments (
    timestamp              TEXT  NOT NULL UNIQUE,
    experiment             TEXT  NOT NULL
);
