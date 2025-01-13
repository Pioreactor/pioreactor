
--- see triggers for how this is populated!
CREATE TABLE IF NOT EXISTS experiment_worker_assignments_history (
    pioreactor_unit TEXT NOT NULL,
    experiment TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    unassigned_at TEXT,
    UNIQUE (pioreactor_unit, experiment, assigned_at)
);

CREATE INDEX IF NOT EXISTS idx_experiment_worker_assignments_history
    ON experiment_worker_assignments_history (
        experiment,
        pioreactor_unit,
        assigned_at,
        unassigned_at
    );



CREATE TRIGGER IF NOT EXISTS insert_experiment_worker_assignments_history
AFTER INSERT
ON experiment_worker_assignments
FOR EACH ROW
BEGIN
    INSERT INTO experiment_worker_assignments_history (
        pioreactor_unit,
        experiment,
        assigned_at
    )
    VALUES (
        NEW.pioreactor_unit,
        NEW.experiment,
        NEW.assigned_at
    );
END;

CREATE TRIGGER IF NOT EXISTS delete_experiment_worker_assignments_history
AFTER DELETE
ON experiment_worker_assignments
FOR EACH ROW
BEGIN
    UPDATE experiment_worker_assignments_history
        SET unassigned_at = STRFTIME('%Y-%m-%dT%H:%M:%f000Z', 'NOW')
    WHERE pioreactor_unit = OLD.pioreactor_unit
        AND experiment = OLD.experiment
        AND assigned_at = OLD.assigned_at
        AND unassigned_at IS NULL;
END;


-- populate with existing data
INSERT OR IGNORE INTO experiment_worker_assignments_history (
    pioreactor_unit,
    experiment,
    assigned_at
)
SELECT
    pioreactor_unit,
    experiment,
    assigned_at
FROM experiment_worker_assignments;
