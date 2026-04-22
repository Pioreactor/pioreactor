# -*- coding: utf-8 -*-
from unittest.mock import Mock

from pioreactor.web import api


def test_start_stirring_calibration_batch(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_save(batch):
        captured["batch"] = batch

    fake_task = Mock()
    fake_task.id = "task-1"

    monkeypatch.setattr(api.tasks, "save_calibration_batch", fake_save)
    monkeypatch.setattr(api.tasks, "run_stirring_calibration_batch", lambda batch_id, units: fake_task)

    response = client.post("/api/calibration_batches/stirring", json={"units": ["unit1", "unit2"]})

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["task_id"] == "task-1"
    assert payload["batch"]["protocol_name"] == "dc_based"
    assert payload["batch"]["target_device"] == "stirring"
    assert payload["batch"]["units"]["unit1"]["status"] == "pending"
    assert captured["batch"]["batch_id"] == payload["batch"]["batch_id"]


def test_get_stirring_calibration_batch(client, monkeypatch) -> None:
    monkeypatch.setattr(
        api.tasks,
        "load_calibration_batch",
        lambda batch_id: {
            "batch_id": batch_id,
            "status": "running",
            "units": {"unit1": {"status": "running"}},
        },
    )

    response = client.get("/api/calibration_batches/stirring/batch-1")

    assert response.status_code == 200
    assert response.get_json()["batch"]["batch_id"] == "batch-1"


def test_abort_stirring_calibration_batch(client, monkeypatch) -> None:
    batch = {
        "batch_id": "batch-1",
        "status": "running",
        "units": {
            "unit1": {"status": "running", "session_id": "session-1"},
            "unit2": {"status": "pending"},
        },
    }
    saved_batches: list[dict[str, object]] = []

    monkeypatch.setattr(api.tasks, "load_calibration_batch", lambda batch_id: batch)
    monkeypatch.setattr(
        api.tasks, "save_calibration_batch", lambda payload: saved_batches.append(payload.copy())
    )
    post_into = Mock()
    monkeypatch.setattr(api, "post_into", post_into)
    monkeypatch.setattr(api, "resolve_to_address", lambda unit: f"http://{unit}")

    response = client.post("/api/calibration_batches/stirring/batch-1/abort")

    assert response.status_code == 200
    payload = response.get_json()["batch"]
    assert payload["status"] == "aborted"
    assert payload["units"]["unit1"]["status"] == "aborted"
    assert payload["units"]["unit2"]["status"] == "aborted"
    post_into.assert_called_once_with(
        "http://unit1", "/unit_api/calibrations/sessions/session-1/abort", timeout=30
    )
    assert len(saved_batches) == 2
