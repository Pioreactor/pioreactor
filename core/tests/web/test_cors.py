# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from pioreactor.web import cors
from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def shared_config(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    (tmp_path / "config.ini").write_text("[cluster.addresses]\nunit2=192.168.1.42\n")
    monkeypatch.setattr(cors, "get_dot_pioreactor_path", lambda: tmp_path)
    cors.clear_allowed_hosts_cache()
    yield tmp_path
    cors.clear_allowed_hosts_cache()


def _get(client: FlaskClient, origin: str | None):
    headers = {"Origin": origin} if origin else {}
    return client.get("/api/workers", headers=headers)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://unit1",
        "http://unit1.local",
        "http://UNIT1.local",
        "http://192.168.1.42",
    ],
)
def test_allowed_origins_get_cors_headers(client: FlaskClient, origin: str) -> None:
    response = _get(client, origin)

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]
    assert "X-Pioreactor-Target" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Access-Control-Max-Age"] == "600"
    assert "Origin" in response.headers["Vary"]
    assert "Access-Control-Allow-Credentials" not in response.headers


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "http://unit1.evil.example.com",
        "http://unit1:8080",
        "http://notaunit.local",
        "null",
        "file://",
        "ftp://unit1",
    ],
)
def test_other_origins_get_no_cors_headers(client: FlaskClient, origin: str) -> None:
    response = _get(client, origin)

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Origin" in response.headers["Vary"]


def test_no_origin_means_no_cors_headers(client: FlaskClient) -> None:
    response = _get(client, None)
    assert "Access-Control-Allow-Origin" not in response.headers


def test_preflight_is_answered_for_json_writes(client: FlaskClient) -> None:
    response = client.options(
        "/api/experiments/exp1/workers",
        headers={
            "Origin": "http://unit1.local",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://unit1.local"
    assert "PUT" in response.headers["Access-Control-Allow-Methods"]


def test_error_responses_are_readable_cross_origin(client: FlaskClient) -> None:
    response = client.get("/api/does_not_exist", headers={"Origin": "http://unit1.local"})

    assert response.status_code == 404
    assert response.headers["Access-Control-Allow-Origin"] == "http://unit1.local"


def test_unit_api_is_unaffected(client: FlaskClient) -> None:
    response = client.get("/unit_api/health", headers={"Origin": "http://unit1.local"})

    assert "Access-Control-Allow-Origin" not in response.headers
