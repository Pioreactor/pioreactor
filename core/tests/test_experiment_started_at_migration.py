# -*- coding: utf-8 -*-
import runpy
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
MIGRATION = REPO_ROOT / "core/update_scripts/upcoming/migrate_experiment_started_at.py"


def test_start_time_migration_preserves_history_and_is_idempotent() -> None:
    schema = (REPO_ROOT / "packaging/shared-assets/sql/create_tables.sql").read_text(encoding="utf-8")
    old_schema = schema.replace("    started_at TEXT NOT NULL,\n", "", 1)
    old_schema = old_schema.replace("    started_at,\n    description,", "    description,")
    old_schema = old_schema.replace('strftime("%s", started_at)', 'strftime("%s", created_at)')
    migrate = runpy.run_path(str(MIGRATION))["migrate"]

    with sqlite3.connect(":memory:") as connection:
        connection.executescript(old_schema)
        connection.executescript(
            """
            INSERT INTO experiments (rowid, experiment, created_at, description) VALUES
                (2, 'exp1', '2023-10-01T12:00:00Z', 'first'),
                (9, 'exp3', '2023-09-01T12:00:00Z', 'latest inserted');
            INSERT INTO workers (pioreactor_unit, added_at, is_active) VALUES ('unit1', '2023-10-01', 1);
            INSERT INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at)
                VALUES ('unit1', 'exp1', '2023-10-01');
            INSERT INTO experiment_tags (experiment, tag, created_at) VALUES ('exp1', 'keep', '2023-10-01');
            INSERT INTO dosing_events (experiment, pioreactor_unit, timestamp, event, volume_change_ml)
                VALUES ('exp1', 'unit1', '2023-10-01T12:00:00Z', 'add_media', 2.0);
        """
        )
        connection.execute("PRAGMA foreign_keys = ON")
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {
            table: connection.execute(f'SELECT rowid, * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }

        migrate(connection)

        assert connection.execute("SELECT experiment FROM latest_experiment").fetchone() == ("exp3",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        for table in tables:
            if table == "experiments":
                rows = connection.execute(
                    "SELECT rowid, experiment, created_at, description FROM experiments ORDER BY rowid"
                ).fetchall()
            else:
                rows = connection.execute(f'SELECT rowid, * FROM "{table}" ORDER BY rowid').fetchall()
            assert rows == before[table]
        assert connection.execute(
            "SELECT started_at FROM experiments WHERE experiment='exp1'"
        ).fetchone() == ("2023-10-01T12:00:00.000Z",)
        connection.execute(
            "UPDATE experiments SET started_at='2026-10-31T12:00:00.000Z' WHERE experiment='exp1'"
        )
        connection.commit()
        migrate(connection)
        assert connection.execute(
            "SELECT started_at FROM experiments WHERE experiment='exp1'"
        ).fetchone() == ("2026-10-31T12:00:00.000Z",)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO experiments (experiment, created_at) VALUES ('invalid', 'now')")


def test_start_time_migration_rolls_back_invalid_creation_time() -> None:
    migrate = runpy.run_path(str(MIGRATION))["migrate"]
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            """
            CREATE TABLE experiments (experiment TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, description TEXT);
            INSERT INTO experiments VALUES ('old', 'invalid', 'keep me');
            CREATE VIEW latest_experiment AS SELECT * FROM experiments;
        """
        )
        with pytest.raises(sqlite3.IntegrityError):
            migrate(connection)
        assert connection.execute("SELECT * FROM latest_experiment").fetchone() == (
            "old",
            "invalid",
            "keep me",
        )
        assert "started_at" not in [row[1] for row in connection.execute("PRAGMA table_info(experiments)")]
