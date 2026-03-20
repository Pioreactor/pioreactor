# -*- coding: utf-8 -*-
import sqlite3

import pytest
from flask import g


def _prepare_db_file(tmp_path) -> str:
    db_path = tmp_path / "test_writable.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE demo (x INTEGER)")
    conn.execute("INSERT INTO demo (x) VALUES (1)")
    conn.commit()
    conn.close()
    return str(db_path)


def _count_rows(path: str) -> int:
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute("SELECT COUNT(*) FROM demo")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def test_query_app_db_disallows_dml_via_query_only_pragma(app, tmp_path) -> None:
    from pioreactor.web.app import _make_dicts, query_app_db

    db_path = _prepare_db_file(tmp_path)

    # Sanity: 1 seed row exists
    assert _count_rows(db_path) == 1

    # Attempt INSERT via query_app_db: should be blocked by PRAGMA query_only
    with app.app_context():
        g._app_database = sqlite3.connect(db_path)
        g._app_database.row_factory = _make_dicts
        with pytest.raises(sqlite3.OperationalError):
            query_app_db("INSERT INTO demo(x) VALUES (2)")

    # Attempt DELETE via query_app_db: should be blocked
    with app.app_context():
        g._app_database = sqlite3.connect(db_path)
        g._app_database.row_factory = _make_dicts
        with pytest.raises(sqlite3.OperationalError):
            query_app_db("DELETE FROM demo")

    # Still unchanged
    assert _count_rows(db_path) == 1


def test_app_db_enables_recursive_triggers_for_assignment_history(app, monkeypatch, tmp_path) -> None:
    from pioreactor.web import app as web_app

    db_path = tmp_path / "assignment_history.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE workers (
                pioreactor_unit TEXT NOT NULL,
                added_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1 NOT NULL,
                UNIQUE(pioreactor_unit)
            );

            CREATE TABLE experiments (
                experiment TEXT PRIMARY KEY
            );

            CREATE TABLE experiment_worker_assignments (
                pioreactor_unit TEXT NOT NULL,
                experiment TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                UNIQUE(pioreactor_unit),
                FOREIGN KEY (pioreactor_unit) REFERENCES workers(pioreactor_unit) ON DELETE CASCADE,
                FOREIGN KEY (experiment) REFERENCES experiments(experiment) ON DELETE CASCADE
            );

            CREATE TABLE experiment_worker_assignments_history (
                pioreactor_unit TEXT NOT NULL,
                experiment TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                unassigned_at TEXT,
                UNIQUE (pioreactor_unit, experiment, assigned_at)
            );

            CREATE TRIGGER insert_experiment_worker_assignments_history
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

            CREATE TRIGGER delete_experiment_worker_assignments_history
            AFTER DELETE
            ON experiment_worker_assignments
            FOR EACH ROW
            BEGIN
                UPDATE experiment_worker_assignments_history
                    SET unassigned_at = OLD.assigned_at
                WHERE pioreactor_unit = OLD.pioreactor_unit
                    AND experiment = OLD.experiment
                    AND assigned_at = OLD.assigned_at
                    AND unassigned_at IS NULL;
            END;

            INSERT INTO workers (pioreactor_unit, added_at, is_active)
            VALUES ('pio01', '2026-01-01T00:00:00Z', 1);

            INSERT INTO experiments (experiment)
            VALUES ('exp1'), ('exp2');
            """
        )
        conn.commit()
    finally:
        conn.close()

    original_get = web_app.pioreactor_config.get

    def fake_config_get(section: str, option: str, *args, **kwargs):
        if section == "storage" and option == "database":
            return str(db_path)
        return original_get(section, option, *args, **kwargs)

    monkeypatch.setattr(web_app.pioreactor_config, "get", fake_config_get)

    with app.app_context():
        pragma = web_app.query_app_db("PRAGMA recursive_triggers;", one=True)
        assert pragma == {"recursive_triggers": 1}

        first_assigned_at = "2026-03-20T16:00:00Z"
        second_assigned_at = "2026-03-20T17:00:00Z"

        assert (
            web_app.modify_app_db(
                "INSERT OR REPLACE INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) VALUES (?, ?, ?)",
                ("pio01", "exp1", first_assigned_at),
            )
            == 1
        )
        assert (
            web_app.modify_app_db(
                "INSERT OR REPLACE INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) VALUES (?, ?, ?)",
                ("pio01", "exp2", second_assigned_at),
            )
            == 1
        )

        history_rows = web_app.query_app_db(
            """
            SELECT experiment, assigned_at, unassigned_at
            FROM experiment_worker_assignments_history
            ORDER BY assigned_at
            """
        )

    assert history_rows == [
        {
            "experiment": "exp1",
            "assigned_at": first_assigned_at,
            "unassigned_at": first_assigned_at,
        },
        {
            "experiment": "exp2",
            "assigned_at": second_assigned_at,
            "unassigned_at": None,
        },
    ]
