# -*- coding: utf-8 -*-
from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import save_local_model
from pioreactor.utils.job_manager import JobManager
from pioreactor.web import tasks

MODEL = {"model_name": "pioreactor_20ml", "model_version": "1.5"}


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
        assert client.get("/unit_api/model").get_json() == MODEL
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
