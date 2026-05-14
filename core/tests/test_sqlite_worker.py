# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

from pioreactor.utils.sqlite_worker import Sqlite3Worker
from pioreactor.utils.sqlite_worker import SqliteValues


def test_sqlite_worker_reports_async_write_errors(tmp_path: Path) -> None:
    errors: list[tuple[Exception, str]] = []

    def collect_error(error: Exception, query: str, values: SqliteValues) -> None:
        errors.append((error, query))

    db_path = tmp_path / "worker.sqlite"
    worker = Sqlite3Worker(db_path.as_posix(), raise_on_error=False, on_error=collect_error)
    try:
        worker.execute("CREATE TABLE test_table (id INTEGER)")
        worker.execute("INSERT INTO missing_table (id) VALUES (?)", (1,))
        worker.execute("INSERT INTO test_table (id) VALUES (?)", (2,))
    finally:
        worker.close()

    assert len(errors) == 1
    assert isinstance(errors[0][0], sqlite3.Error)
    assert "missing_table" in errors[0][1]

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT id FROM test_table").fetchall() == [(2,)]
