# -*- coding: utf-8 -*-
from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient
from msgspec import to_builtins
from msgspec.json import encode
from pioreactor.models import get_registered_models
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import report_model_to_leader
from pioreactor.unit_model import save_local_model
from pioreactor.utils.job_manager import JobManager
from pioreactor.web import tasks
from pioreactor.whoami import get_unit_name

MODEL = {"model_name": "pioreactor_20ml", "model_version": "1.5"}
WORKER_ONLY_MODEL = {
    "model_name": "custom_bench_reactor",
    "model_version": "0.1",
    "display_name": "Custom bench reactor",
    "reactor_capacity_ml": 30.0,
    "reactor_diameter_mm": 27.0,
    "reactor_max_fill_volume_ml": 28.0,
    "max_temp_to_reduce_heating": 63.0,
    "max_temp_to_disable_heating": 65.0,
    "max_temp_to_shutdown": 66.0,
    "is_legacy": False,
    "is_contrib": True,
}


@pytest.fixture(autouse=True)
def unit_model_reads(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """The worker's GET /unit_api/model, offline unless a test sets a return value."""
    reported = Mock(return_value=None)

    def get_from(address: str, endpoint: str, **kwargs: object) -> Response:
        assert endpoint == "/unit_api/model"
        if reported() is None:
            raise HTTPException("offline")
        return Response("http://unit", 200, {}, encode(reported()))

    monkeypatch.setattr("pioreactor.web.api.get_from", get_from)
    return reported


def accept_assignment(client: FlaskClient, monkeypatch: pytest.MonkeyPatch, model: dict) -> None:
    accepted = Response("http://unit", 200, {}, b"{}")
    monkeypatch.setattr("pioreactor.web.api.put_into", Mock(return_value=accepted))
    body = {"model_name": model["model_name"], "model_version": model["model_version"]}
    assert client.put("/api/workers/unit1/model", json=body).status_code == 200


def test_unit_model_unset_and_validation(client: FlaskClient) -> None:
    assert client.get("/unit_api/model").status_code == 404
    assert client.put("/unit_api/model", json={}).status_code == 400
    assert client.put("/unit_api/model", json={**MODEL, "model_name": "unknown"}).status_code == 400
    assert get_local_model() is None


@pytest.mark.parametrize("long_running", [True, False])
def test_unit_model_requires_ordinary_activities_stopped(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, long_running: bool
) -> None:
    save_local_model("pioreactor_40ml", "1.5")
    with JobManager() as manager:
        manager.register_and_set_running(
            unit="unit1",
            experiment="exp",
            job_name="plugin_job",
            job_source="test",
            pid=123456,
            leader="leader",
            is_long_running_job=long_running,
        )
    check = Mock()
    monkeypatch.setattr(tasks, "check_model_hardware", check)
    response = client.put("/unit_api/model", json=MODEL)
    assert response.status_code == (200 if long_running else 409)
    if long_running:
        assert client.get("/unit_api/model").get_json().items() >= MODEL.items()
        check.assert_called_once_with("pioreactor_20ml", "1.5")
    else:
        assert get_local_model() == ("pioreactor_40ml", "1.5")
        check.assert_not_called()


@pytest.mark.parametrize("status", [200, 409, None])
def test_leader_only_updates_mirror_after_success(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, status: int | None
) -> None:
    before = client.get("/api/workers/unit1/model").get_json()
    response = Response(
        "http://unit",
        status or 200,
        {},
        b'{"error":"Stop activities before changing the model.","status":409}',
    )
    put = Mock(side_effect=HTTPException("offline")) if status is None else Mock(return_value=response)
    monkeypatch.setattr("pioreactor.web.api.put_into", put)
    result = client.put("/api/workers/unit1/model", json=MODEL)
    assert result.status_code == (status if status is not None else 502)
    after = client.get("/api/workers/unit1/model").get_json()
    assert after["model_name"] == (MODEL["model_name"] if status == 200 else before["model_name"])
    assert after["model_version"] == (MODEL["model_version"] if status == 200 else before["model_version"])
    assert put.call_args.kwargs["headers"] == {"X-Pioreactor-Target": "unit1"}


def test_unit_model_includes_its_registry_definition(client: FlaskClient) -> None:
    save_local_model("pioreactor_20ml", "1.5")
    expected = to_builtins(get_registered_models()[("pioreactor_20ml", "1.5")])
    assert client.get("/unit_api/model").get_json() == expected


def test_leader_reads_worker_only_model_from_the_worker(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock
) -> None:
    assert ("custom_bench_reactor", "0.1") not in get_registered_models()
    accept_assignment(client, monkeypatch, WORKER_ONLY_MODEL)
    unit_model_reads.return_value = WORKER_ONLY_MODEL

    response = client.get("/api/workers/unit1/model")

    assert response.status_code == 200
    assert response.get_json() == {"pioreactor_unit": "unit1", **WORKER_ONLY_MODEL}


def test_unreadable_model_is_a_clear_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock
) -> None:
    accept_assignment(client, monkeypatch, WORKER_ONLY_MODEL)

    response = client.get("/api/workers/unit1/model")

    assert response.status_code == 409
    assert "custom_bench_reactor" in response.get_json()["error"]


def test_worker_definition_wins_over_leader_registry(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock
) -> None:
    accept_assignment(client, monkeypatch, MODEL)
    leader_definition = to_builtins(get_registered_models()[("pioreactor_20ml", "1.5")])
    unit_model_reads.return_value = {**leader_definition, "reactor_max_fill_volume_ml": 12.0}

    assert client.get("/api/workers/unit1/model").get_json()["reactor_max_fill_volume_ml"] == 12.0


def test_worker_answer_wins_even_when_the_mirror_differs(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock
) -> None:
    accept_assignment(client, monkeypatch, MODEL)
    unit_model_reads.return_value = WORKER_ONLY_MODEL

    assert client.get("/api/workers/unit1/model").get_json() == {
        "pioreactor_unit": "unit1",
        **WORKER_ONLY_MODEL,
    }


@pytest.mark.parametrize("reported", [None, MODEL])
def test_leader_registry_covers_offline_and_older_workers(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock, reported: dict | None
) -> None:
    accept_assignment(client, monkeypatch, MODEL)
    # None is an offline worker; MODEL alone is an older worker's name-and-version answer.
    unit_model_reads.return_value = reported

    response = client.get("/api/workers/unit1/model")

    assert response.status_code == 200
    assert response.get_json() == {
        "pioreactor_unit": "unit1",
        **to_builtins(get_registered_models()[("pioreactor_20ml", "1.5")]),
    }


def test_reported_model_updates_only_the_mirror(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, unit_model_reads: Mock
) -> None:
    forward = Mock(side_effect=AssertionError("must not forward to the unit"))
    monkeypatch.setattr("pioreactor.web.api.put_into", forward)
    body = {
        "model_name": WORKER_ONLY_MODEL["model_name"],
        "model_version": WORKER_ONLY_MODEL["model_version"],
    }

    # The unit's registry decides what's valid, so a model unknown to the leader is accepted.
    assert client.put("/api/workers/unit1/reported_model", json=body).status_code == 200
    assert client.put("/api/workers/unit1/reported_model", json=body).status_code == 200

    unit_model_reads.return_value = WORKER_ONLY_MODEL
    assert client.get("/api/workers/unit1/model").get_json()["model_name"] == "custom_bench_reactor"
    forward.assert_not_called()


def test_reported_model_from_unknown_worker_is_rejected(client: FlaskClient) -> None:
    response = client.put("/api/workers/not_a_worker/reported_model", json=MODEL)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("outcome", "reported"),
    [
        (Response("http://leader", 200, {}, b"{}"), True),
        (Response("http://leader", 404, {}, b"{}"), False),
        (HTTPException("offline"), False),
    ],
)
def test_report_model_to_leader_is_best_effort(
    monkeypatch: pytest.MonkeyPatch, outcome: Response | HTTPException, reported: bool
) -> None:
    put = Mock(side_effect=outcome) if isinstance(outcome, HTTPException) else Mock(return_value=outcome)
    monkeypatch.setattr("pioreactor.pubsub.put_into", put)

    assert report_model_to_leader("10.0.0.1", "pioreactor_20ml", "1.5") is reported
    assert put.call_args.args == ("10.0.0.1", f"/api/workers/{get_unit_name()}/reported_model")
    assert put.call_args.kwargs["json"] == MODEL
