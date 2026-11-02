#!/opt/pioreactor/venv/bin/python
# -*- coding: utf-8 -*-
"""Separate immutable experiment creation from editable scientific time zero."""
import sqlite3
import sys
from pathlib import Path


def migrate(connection: sqlite3.Connection) -> None:
    if any(row[1] == "started_at" for row in connection.execute("PRAGMA table_info(experiments)")):
        return

    # Rebuild only the small parent table; retain rowids and all child data.
    # Foreign-key enforcement must be disabled before entering the transaction.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            # Validate only this small table, not the potentially gigabytes of child data.
            expected_rows = connection.execute(
                """SELECT rowid, experiment, created_at,
                          strftime('%Y-%m-%dT%H:%M:%fZ', created_at), description
                   FROM experiments ORDER BY rowid"""
            ).fetchall()
            connection.execute("DROP VIEW IF EXISTS latest_experiment")
            connection.execute(
                """CREATE TABLE experiments_new (
                    experiment TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    description TEXT
                )"""
            )
            connection.execute(
                """INSERT INTO experiments_new (rowid, experiment, created_at, started_at, description)
                SELECT rowid, experiment, created_at,
                       strftime('%Y-%m-%dT%H:%M:%fZ', created_at), description
                FROM experiments"""
            )
            connection.execute("DROP TABLE experiments")
            connection.execute("ALTER TABLE experiments_new RENAME TO experiments")
            connection.execute(
                "CREATE UNIQUE INDEX experiments_ix ON experiments (created_at, experiment, description)"
            )
            connection.execute(
                """CREATE VIEW latest_experiment AS
                SELECT experiment, created_at, started_at, description,
                       round((strftime('%s', 'now') - strftime('%s', started_at)) / 60 / 60, 0)
                           AS delta_hours
                FROM experiments ORDER BY rowid DESC LIMIT 1"""
            )
            actual_rows = connection.execute(
                "SELECT rowid, experiment, created_at, started_at, description FROM experiments ORDER BY rowid"
            ).fetchall()
            if actual_rows != expected_rows:
                raise RuntimeError("Experiment start-time migration changed experiment records")
            expected_latest = [(expected_rows[-1][1],)] if expected_rows else []
            if connection.execute("SELECT experiment FROM latest_experiment").fetchall() != expected_latest:
                raise RuntimeError("Experiment start-time migration changed the latest experiment")
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


if __name__ == "__main__":
    database = Path(sys.argv[1])
    # mode=rw prevents a wrong path from creating an empty database.
    connection = sqlite3.connect(f"{database.absolute().as_uri()}?mode=rw", uri=True, timeout=15)
    try:
        migrate(connection)
    finally:
        connection.close()
