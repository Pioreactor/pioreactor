# update.sql

# TODO: this table is old!!
CREATE TABLE IF NOT EXISTS experiment_worker_assignments (
    pioreactor_unit     TEXT NOT NULL,
    experiment          TEXT NOT NULL,
    assigned_at         TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_active           INTEGER DEFAULT 1 NOT NULL,
    UNIQUE(pioreactor_unit, experiment)
);


## TODO: add new experiments column to table experiment_profile_runs
