PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiment_unit_colors (
    experiment TEXT NOT NULL,
    pioreactor_unit TEXT NOT NULL,
    color TEXT NOT NULL,
    PRIMARY KEY (experiment, pioreactor_unit),
    FOREIGN KEY (experiment) REFERENCES experiments (
        experiment
    ) ON DELETE CASCADE
);
