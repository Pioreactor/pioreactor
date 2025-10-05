# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from flask import g
from msgspec import Struct
from msgspec import to_builtins
from pioreactor.mureq import get
from pioreactor.mureq import Response
from pioreactor.web.app import _make_dicts
from pioreactor.web.app import create_app


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
        }
    )

    with app.app_context():
        r = get(
            "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/refs/heads/pioreactor/workspace/scripts/files/sql/create_tables.sql"
        )
        table_statements = r.body.decode()

        db = getattr(g, "_app_database", None)
        if db is None:
            db = g._app_database = sqlite3.connect(":memory:")
            db.row_factory = _make_dicts
            db.executescript(table_statements)  # Set up schema
            sql_path = Path(__file__).parent / "example_data.sql"
            with sql_path.open("rb") as f:
                db.executescript(f.read().decode("utf8"))

            db.commit()

        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class CapturedRequest:
    def __init__(self, method, url, headers, body, json):
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.json = json

        r = urlparse(url)

        self.path = r.path

    def __lt__(self, other):
        return self.path < other.path

    def __repr__(self):
        return f"CaptureRequest(url={self.url}, method={self.method})"


@contextlib.contextmanager
def capture_requests():
    bucket = []

    def mock_request(method, url, **kwargs):
        # Capture the request details
        headers = kwargs.get("headers")
        body = kwargs.get("body", None)
        json = kwargs.get("json", None)
        if isinstance(json, Struct):
            json = to_builtins(json)
        bucket.append(CapturedRequest(method, url, headers, body, json))
        # Return a mock response object
        return Response(url, 200, {}, b'{"mocked": "response"}')

    # Patch the mureq.request method
    with patch("pioreactor.mureq.request", side_effect=mock_request):
        yield bucket
