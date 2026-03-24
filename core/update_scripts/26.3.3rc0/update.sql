PRAGMA busy_timeout = 15000;
PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;

WITH repaired AS (
    SELECT
        h.rowid AS row_id,
        COALESCE(
            (
                SELECT MIN(h2.assigned_at)
                FROM experiment_worker_assignments_history AS h2
                WHERE h2.pioreactor_unit = h.pioreactor_unit
                  AND h2.assigned_at > h.assigned_at
            ),
            STRFTIME('%Y-%m-%dT%H:%M:%f000Z', 'NOW')
        ) AS repaired_unassigned_at
    FROM experiment_worker_assignments_history AS h
    WHERE h.unassigned_at IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM experiment_worker_assignments AS a
          WHERE a.pioreactor_unit = h.pioreactor_unit
            AND a.experiment = h.experiment
            AND a.assigned_at = h.assigned_at
      )
)
UPDATE experiment_worker_assignments_history
SET unassigned_at = (
    SELECT repaired.repaired_unassigned_at
    FROM repaired
    WHERE repaired.row_id = experiment_worker_assignments_history.rowid
)
WHERE rowid IN (SELECT row_id FROM repaired);
