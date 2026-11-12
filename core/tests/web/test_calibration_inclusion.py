# -*- coding: utf-8 -*-
from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient
from pioreactor import calibrations
from pioreactor import structs
from pioreactor.utils import local_persistent_storage
from pioreactor.web import cache
from pioreactor.web import tasks


@pytest.mark.parametrize("active", [False, True])
def test_patch_saved_calibration(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, active: bool
) -> None:
    monkeypatch.setattr(tasks.huey, "_immediate", True)
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    cal = structs.SimplePeristalticPumpCalibration(
        calibration_name="mask-api",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(timezone.utc),
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
        recorded_data={"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 20.0]},
        hz=250.0,
        dc=60.0,
        voltage=5.0,
    )
    cal.save_to_disk_for_device("media_pump")
    with local_persistent_storage("active_calibrations") as storage:
        storage.pop("media_pump", None)
        if active:
            storage["media_pump"] = cal.calibration_name
    response = client.patch(
        "/unit_api/calibrations/media_pump/mask-api",
        json={
            "included": [True, True, False],
            "y_values": [0.0, 2.0, 40.1234567890123],
            "x_values": [0.0, 2.0, 3.1234567890123],
        },
    )
    assert response.status_code == 202
    completed = client.get(response.json["result_url_path"])
    assert completed.json["status"] == "succeeded"
    assert completed.json["result"]["is_active"] is active
    loaded = calibrations.load_calibration("media_pump", "mask-api")
    assert loaded.included == [True, True, False]
    assert loaded.recorded_data["x"] == [0.0, 2.0, 3.1234567890123]
    assert loaded.recorded_data["y"] == [0.0, 2.0, 40.1234567890123]
    assert loaded.x_to_y(1.0) == pytest.approx(1.0)
    before = loaded.path_on_disk_for_device("media_pump").read_bytes()
    response = client.patch(
        "/unit_api/calibrations/media_pump/mask-api", json={"included": [True, False, False]}
    )
    completed = client.get(response.json["result_url_path"])
    assert completed.json["status"] == "failed"
    assert "distinct x" in completed.json["error"]
    assert loaded.path_on_disk_for_device("media_pump").read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        {"included": [1]},
        {"included": ["true"]},
        {"included": None},
        {"included": [True], "recorded_data": {}},
        {"included": [True], "y_values": [True]},
        {"included": [True], "y_values": ["bad"]},
        {"included": [True], "z_values": [2.0]},
    ],
)
def test_patch_rejects_invalid_request(client: FlaskClient, body: dict) -> None:
    assert client.patch("/unit_api/calibrations/media_pump/mask-api", json=body).status_code == 400


def test_leader_invalidates_after_worker_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    def request(*args: object, **kwargs: object) -> tuple[str, dict]:
        events.append("persisted")
        return "unit1", {"ok": True, "value": {"included": [True, False]}}

    monkeypatch.setattr(tasks, "_request_unit", request)
    monkeypatch.setattr(cache, "invalidate_calibrations_cache", lambda unit: events.append("invalidated"))
    result = tasks.update_worker_calibration_measurements.call_local("unit1", "od90", "test", [True, False])
    assert events == ["persisted", "invalidated"]
    assert result["unit1"]["ok"]


def test_leader_patch_dispatch(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    task = Mock(return_value=tasks.finished_task_result({"unit1": {"ok": True, "value": {}}}))
    monkeypatch.setattr(tasks, "update_worker_calibration_measurements", task)
    response = client.patch("/api/workers/unit1/calibrations/od90/test", json={"included": [True, False]})
    assert response.status_code == 202
    task.assert_called_once_with("unit1", "od90", "test", [True, False], None, None)
    assert (
        client.patch("/api/workers/$broadcast/calibrations/od90/test", json={"included": [True]}).status_code
        == 400
    )
