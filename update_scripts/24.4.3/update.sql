# update.sql

CREATE TABLE IF NOT EXISTS experiment_worker_assignments (
    pioreactor_unit     TEXT NOT NULL,
    experiment          TEXT NOT NULL,
    assigned_at         TEXT NOT NULL,
    UNIQUE(pioreactor_unit), -- force a worker to only ever be assigned to a single experiment.
    FOREIGN KEY (pioreactor_unit) REFERENCES workers(pioreactor_unit)  ON DELETE CASCADE,
    FOREIGN KEY (experiment) REFERENCES experiments(experiment)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workers (
    pioreactor_unit     TEXT NOT NULL, -- id
    added_at            TEXT NOT NULL,
    is_active           INTEGER DEFAULT 1 NOT NULL,
    UNIQUE(pioreactor_unit)
);



ALTER TABLE experiment_profile_runs
ADD COLUMN experiment TEXT;
