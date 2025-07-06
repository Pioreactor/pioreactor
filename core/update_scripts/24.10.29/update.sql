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
