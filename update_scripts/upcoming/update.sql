DROP TABLE IF EXISTS calibrations;

CREATE TABLE IF NOT EXISTS calibrations (
    pioreactor_unit          TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    type                     TEXT NOT NULL,
    data                     TEXT NOT NULL,
    name                     TEXT NOT NULL,
    is_current               INTEGER DEFAULT 0 NOT NULL,
    set_to_current_at        TEXT,
    UNIQUE(pioreactor_unit, type, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS calibrations_ix
ON calibrations (pioreactor_unit, type, name);
