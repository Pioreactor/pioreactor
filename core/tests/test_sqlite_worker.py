# -*- coding: utf-8 -*-
import sqlite3
import time
from pathlib import Path
from typing import Any
from typing import Callable

import pioreactor.utils.sqlite_worker as sqlite_worker_module
import pytest
from pioreactor.utils.sqlite_worker import Sqlite3Worker
from pioreactor.utils.sqlite_worker import SqliteValues


class CountingConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.commit_count = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def __enter__(self) -> sqlite3.Connection:
        return self.connection.__enter__()

    def __exit__(self, *args: object) -> bool | None:
        return self.connection.__exit__(*args)

    def commit(self) -> None:
        self.commit_count += 1
        self.connection.commit()


def wait_until(predicate: Callable[[], bool], timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)

    raise AssertionError("Timed out waiting for predicate.")


def create_worker_with_commit_counter(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, **kwargs: object
) -> tuple[Sqlite3Worker, CountingConnection]:
    original_connect = sqlite_worker_module.sqlite3.connect
    connection_holder: list[CountingConnection] = []

    def connect(*args: object, **connect_kwargs: object) -> CountingConnection:
        connection = CountingConnection(original_connect(*args, **connect_kwargs))
        connection_holder.append(connection)
        return connection

    monkeypatch.setattr(sqlite_worker_module.sqlite3, "connect", connect)
    worker = Sqlite3Worker(db_path.as_posix(), **kwargs)
    return worker, connection_holder[0]


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


def test_sqlite_worker_rejects_select_queries(tmp_path: Path) -> None:
    worker = Sqlite3Worker((tmp_path / "worker.sqlite").as_posix())
    try:
        with pytest.raises(ValueError, match="write-only"):
            worker.execute("SELECT 1")
    finally:
        worker.close()


def test_sqlite_worker_batches_steady_writes_until_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "worker.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE test_table (id INTEGER)")

    worker, connection = create_worker_with_commit_counter(
        monkeypatch,
        db_path,
        max_batch_delay_s=0.05,
    )
    try:
        worker.execute("INSERT INTO test_table (id) VALUES (?)", (1,))
        worker.execute("INSERT INTO test_table (id) VALUES (?)", (2,))
        wait_until(lambda: connection.commit_count == 1)
    finally:
        worker.close()

    assert connection.commit_count == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT id FROM test_table ORDER BY id").fetchall() == [(1,), (2,)]


def test_sqlite_worker_flushes_quiet_write_after_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "worker.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE test_table (id INTEGER)")

    worker, connection = create_worker_with_commit_counter(
        monkeypatch,
        db_path,
        max_batch_delay_s=0.03,
    )
    try:
        worker.execute("INSERT INTO test_table (id) VALUES (?)", (1,))
        wait_until(lambda: connection.commit_count == 1)
    finally:
        worker.close()

    assert connection.commit_count == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT id FROM test_table").fetchall() == [(1,)]


def test_sqlite_worker_close_flushes_pending_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "worker.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE test_table (id INTEGER)")

    worker, connection = create_worker_with_commit_counter(
        monkeypatch,
        db_path,
        max_batch_delay_s=60,
    )
    worker.execute("INSERT INTO test_table (id) VALUES (?)", (1,))
    worker.close()

    assert connection.commit_count == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT id FROM test_table").fetchall() == [(1,)]
