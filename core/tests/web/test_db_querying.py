# -*- coding: utf-8 -*-
from __future__ import annotations

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


def test_query_app_db_disallows_dml_via_query_only_pragma(app, tmp_path):
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
