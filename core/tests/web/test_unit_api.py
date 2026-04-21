# -*- coding: utf-8 -*-
"""
Additional unit tests for unit_api endpoints.
"""
from datetime import datetime
from datetime import timezone

import pytest
from msgspec.yaml import encode as yaml_encode
from pioreactor.bioreactor import set_bioreactor_value
from pioreactor.structs import PolyFitCoefficients
from pioreactor.structs import SimplePeristalticPumpCalibration
from pioreactor.utils import local_persistent_storage


class FakeTaskResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self, blocking: bool = True, timeout: float | None = None) -> bool:
        return self.value


def _build_valid_calibration_yaml(calibration_name: str) -> str:
    calibration = SimplePeristalticPumpCalibration(
        calibration_name=calibration_name,
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(timezone.utc),
        curve_data_=PolyFitCoefficients(coefficients=[0.0, 1.0]),
        recorded_data={"x": [0.0, 1.0], "y": [0.0, 1.0]},
        hz=250.0,
        dc=60.0,
        voltage=3.3,
    )
    return yaml_encode(calibration).decode()


def test_task_results_pending(client) -> None:
    """GET on non-existent task should return pending status."""
    resp = client.get("/unit_api/task_results/does_not_exist")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "pending"


def test_task_results_complete_is_preserved_across_polls(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    preserve_values: list[bool] = []

    def fake_result(task_id: str, preserve: bool = False) -> dict[str, bool]:
        assert task_id == "task-1"
        preserve_values.append(preserve)
        return {"ok": True}

    monkeypatch.setattr(mod.huey.storage, "has_data_for_key", lambda task_id: task_id == "task-1")
    monkeypatch.setattr(mod.huey, "result", fake_result)

    first = client.get("/unit_api/task_results/task-1")
    second = client.get("/unit_api/task_results/task-1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["status"] == "succeeded"
    assert second.get_json()["status"] == "succeeded"
    assert first.get_json()["result"] == {"ok": True}
    assert second.get_json()["result"] == {"ok": True}
    assert preserve_values == [True, True]


def test_task_results_complete_when_stored_result_is_none(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod.huey.storage, "has_data_for_key", lambda task_id: task_id == "task-2")
    monkeypatch.setattr(mod.huey, "result", lambda task_id, preserve=False: None)

    resp = client.get("/unit_api/task_results/task-2")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "succeeded"
    assert data["result"] is None


def test_task_results_failed_when_taskexception_contains_plain_error(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod
    from huey.exceptions import TaskException

    task_id = "task-3"
    error_message = (
        'RuntimeError("Command exited during startup grace window. Exit code 2. No such command.")'
    )

    monkeypatch.setattr(mod.huey.storage, "has_data_for_key", lambda candidate: candidate == task_id)
    monkeypatch.setattr(
        mod.huey,
        "result",
        lambda candidate, preserve=False: (_ for _ in ()).throw(TaskException({"error": error_message})),
    )

    resp = client.get(f"/unit_api/task_results/{task_id}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "failed"
    assert data["error"] == "Command exited during startup grace window. Exit code 2. No such command."


def test_invalid_update_target(client) -> None:
    """Invalid target for system update should return 404."""
    resp = client.post(
        "/unit_api/system/update/invalid",
        json={"args": [], "options": {}, "env": {}},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data.get("error") == "Invalid target"
    assert data.get("status") == 404
    assert data.get("cause") == "Invalid target"
    assert data.get("remediation") is None


def test_extract_error_message_uses_error_field_only() -> None:
    from pioreactor.web.utils import _extract_error_message

    assert _extract_error_message({"error": " Invalid target "}) == "Invalid target"
    assert _extract_error_message({"description": "Invalid target"}) == "Request failed."


def test_create_task_response_uses_chord_callback_id(client) -> None:
    from pioreactor.web.utils import create_task_response

    class DummyCallback:
        id = "callback-task"

    class DummyChordResult:
        callback = DummyCallback()

    with client.application.app_context():
        response, status_code = create_task_response(DummyChordResult())

    assert status_code == 202
    assert response.get_json()["task_id"] == "callback-task"


@pytest.mark.parametrize("endpoint", ["/unit_api/system/reboot", "/unit_api/system/shutdown"])
def test_reboot_and_shutdown_schedule_task(client, endpoint) -> None:
    """Reboot and shutdown endpoints should schedule background tasks."""
    resp = client.post(endpoint)
    assert resp.status_code == 202
    data = resp.get_json()
    assert "task_id" in data and "result_url_path" in data


def test_get_clock_time_success(client) -> None:
    """GET clock time returns success and a timestamp."""
    resp = client.get("/unit_api/system/utc_clock")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("status") == "success"
    assert "clock_time" in data


def test_set_clock_non_leader(client) -> None:
    resp = client.patch("/unit_api/system/utc_clock", json={})
    assert resp.status_code == 400  # need to provide clock data, else it errors
    data = resp.get_json()
    assert data.get("status") == 400
    assert isinstance(data.get("remediation"), str)


def test_set_clock_time_sync_branch(client, monkeypatch) -> None:
    """When not leader or no payload, sync_clock branch schedules a task."""
    # Force non-leader behavior
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod, "HOSTNAME", "worker1", raising=False)
    monkeypatch.setattr(mod, "get_leader_hostname", lambda: "leader", raising=False)
    resp = client.patch("/unit_api/system/utc_clock")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data.get("result_url_path", "").startswith("/unit_api/task_results/")


def test_get_versions_endpoints(client) -> None:
    r_app = client.get("/unit_api/versions/app")
    assert r_app.status_code == 200
    v_app = r_app.get_json()
    assert "version" in v_app and isinstance(v_app["version"], str)


def test_get_job_descriptors_endpoint_returns_builtin_and_plugin_jobs(client) -> None:
    response = client.get("/unit_api/jobs/descriptors")

    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)

    job_names = {job["job_name"] for job in data}
    assert "stirring" in job_names
    assert "self_test" in job_names


def test_get_automation_descriptors_endpoint_returns_builtin_and_plugin_automations(client) -> None:
    response = client.get("/unit_api/automations/descriptors/dosing")

    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)

    automation_names = {automation["automation_name"] for automation in data}
    assert "chemostat" in automation_names
    assert "turbidostat" in automation_names


def test_get_bioreactor_values_endpoint_returns_defaults(client) -> None:
    resp = client.get("/unit_api/bioreactor/experiments/exp1")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["values"]["current_volume_ml"] == pytest.approx(14.0)
    assert data["values"]["efflux_tube_volume_ml"] == pytest.approx(14.0)
    assert data["values"]["alt_media_fraction"] == pytest.approx(0.0)


def test_get_bioreactor_values_endpoint_returns_persisted_values(client) -> None:
    set_bioreactor_value("exp1", "current_volume_ml", 11.2)
    set_bioreactor_value("exp1", "efflux_tube_volume_ml", 15.0)
    set_bioreactor_value("exp1", "alt_media_fraction", 0.3)

    resp = client.get("/unit_api/bioreactor/experiments/exp1")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["values"]["current_volume_ml"] == pytest.approx(11.2)
    assert data["values"]["efflux_tube_volume_ml"] == pytest.approx(15.0)
    assert data["values"]["alt_media_fraction"] == pytest.approx(0.3)


def test_update_bioreactor_values_endpoint_persists_and_publishes(client, monkeypatch) -> None:
    captured: list[tuple[str, str, str, object]] = []

    def fake_set_and_publish_bioreactor_value(mqtt_client, unit, experiment, variable_name, value) -> float:
        captured.append((unit, experiment, variable_name, value))
        return float(value)

    monkeypatch.setattr(
        "pioreactor.web.unit_api.set_and_publish_bioreactor_value",
        fake_set_and_publish_bioreactor_value,
    )

    resp = client.patch(
        "/unit_api/bioreactor/experiments/exp1",
        json={"values": {"current_volume_ml": 11.2, "alt_media_fraction": 0.3}},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "success"}
    assert captured == [
        ("localhost", "exp1", "current_volume_ml", 11.2),
        ("localhost", "exp1", "alt_media_fraction", 0.3),
    ]


def test_update_bioreactor_values_endpoint_rejects_out_of_range_values(client, monkeypatch) -> None:
    def fake_set_and_publish_bioreactor_value(_mqtt_client, _unit, experiment, variable_name, value) -> float:
        return set_bioreactor_value(experiment, variable_name, value)

    monkeypatch.setattr(
        "pioreactor.web.unit_api.set_and_publish_bioreactor_value",
        fake_set_and_publish_bioreactor_value,
    )

    resp = client.patch(
        "/unit_api/bioreactor/experiments/exp1",
        json={"values": {"efflux_tube_volume_ml": 100.0}},
    )

    assert resp.status_code == 400
    assert "efflux_tube_volume_ml" in resp.get_json()["error"]


def test_run_job_rejects_manual_add_media_that_reaches_safety_threshold(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    set_bioreactor_value("exp1", "current_volume_ml", 12.0)
    monkeypatch.setattr(mod, "is_rate_limited", lambda _job_name: False)
    monkeypatch.setattr(
        mod.tasks,
        "pio_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    response = client.patch(
        "/unit_api/jobs/run/job_name/add_media",
        json={
            "args": [],
            "options": {"ml": 6.0},
            "env": {"EXPERIMENT": "exp1", "MODEL_NAME": "pioreactor_20ml", "MODEL_VERSION": "1.5"},
            "config_overrides": [],
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Requested dose would meet or exceed the reactor safety threshold."


def test_run_job_allows_manual_add_media_below_safety_threshold(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    class DummyTask:
        id = "task-allow-add-media"

    set_bioreactor_value("exp1", "current_volume_ml", 12.0)
    monkeypatch.setattr(mod, "is_rate_limited", lambda _job_name: False)
    monkeypatch.setattr(mod.tasks, "pio_run", lambda *_args, **_kwargs: DummyTask())

    response = client.patch(
        "/unit_api/jobs/run/job_name/add_media",
        json={
            "args": [],
            "options": {"ml": 5.9},
            "env": {"EXPERIMENT": "exp1", "MODEL_NAME": "pioreactor_20ml", "MODEL_VERSION": "1.5"},
            "config_overrides": [],
        },
    )

    assert response.status_code == 202


def test_hardware_check_requires_model_payload(client) -> None:
    resp = client.post("/unit_api/hardware/check", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "Missing model_name or model_version"
    assert data.get("status") == 400
    assert "model_name or model_version" in (data.get("cause") or "")
    assert isinstance(data.get("remediation"), str)


def test_hardware_check_queues_task(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    class DummyTask:
        id = "task-456"

    monkeypatch.setattr(mod.tasks, "check_model_hardware", lambda *_args, **_kwargs: DummyTask())

    resp = client.post(
        "/unit_api/hardware/check",
        json={"model_name": "pioreactor_20ml", "model_version": "1.5"},
    )
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["task_id"] == "task-456"


@pytest.mark.xfail
def test_install_plugin_rejects_without_allowlist(client, monkeypatch, tmp_path) -> None:
    """API install should fail closed if allowlist is missing."""
    import pioreactor.web.unit_api as mod

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setattr(
        mod.tasks,
        "pio_plugins",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    resp = client.post(
        "/unit_api/plugins/install",
        json={"args": ["safe-plugin"], "options": {}, "env": {}},
    )
    assert resp.status_code == 403
    assert b"allowlist" in resp.data


@pytest.mark.xfail
def test_install_plugin_rejects_not_allowlisted(client, monkeypatch) -> None:
    """API install should reject plugins not on the allowlist."""
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(
        mod.tasks,
        "pio_plugins",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    resp = client.post(
        "/unit_api/plugins/install",
        json={"args": ["blocked-plugin"], "options": {}, "env": {}},
    )
    assert resp.status_code == 403
    assert b"allowlist" in resp.data


@pytest.mark.xfail(reason="need to update task api with new plugin install task")
def test_install_plugin_allows_allowlisted(client, monkeypatch) -> None:
    """API install should proceed for allowlisted plugins."""
    import pioreactor.web.unit_api as mod

    captured = {}

    def fake_pio_plugins(*args, **kwargs):
        captured["args"] = args

        class DummyTask:
            id = "task-123"

        return DummyTask()

    monkeypatch.setattr(mod.tasks, "pio_plugins", fake_pio_plugins)

    resp = client.post(
        "/unit_api/plugins/install",
        json={"args": ["pioreactor-air-bubbler"], "options": {}, "env": {}},
    )
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["task_id"] == "task-123"
    assert captured["args"] == ("install", "pioreactor-air-bubbler")


def test_get_jobs_returns_history(client) -> None:
    from time import sleep

    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        old_job_id = jm.register_and_set_running(
            unit="unit1",
            experiment="exp_old",
            job_name="old_job",
            job_source="test",
            pid=1001,
            leader="leader",
            is_long_running_job=False,
        )
        jm.set_not_running(old_job_id)

        sleep(0.02)

        newest_job_id = jm.register_and_set_running(
            unit="unit1",
            experiment="exp_new",
            job_name="new_job",
            job_source="test",
            pid=1002,
            leader="leader",
            is_long_running_job=False,
        )

    response = client.get("/unit_api/jobs")
    assert response.status_code == 200
    rows = response.get_json()
    assert isinstance(rows, list)
    assert [row["job_id"] for row in rows[:2]] == [newest_job_id, old_job_id]
    assert set(rows[0]) == {
        "job_id",
        "job_name",
        "experiment",
        "job_source",
        "unit",
        "started_at",
        "ended_at",
    }


def test_get_running_jobs_endpoint_filters_results(client) -> None:
    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        stopped_job_id = jm.register_and_set_running(
            unit="unit1",
            experiment="exp_old",
            job_name="old_job",
            job_source="test",
            pid=1003,
            leader="leader",
            is_long_running_job=False,
        )
        jm.set_not_running(stopped_job_id)

        running_job_id = jm.register_and_set_running(
            unit="unit1",
            experiment="exp_new",
            job_name="new_job",
            job_source="test",
            pid=1004,
            leader="leader",
            is_long_running_job=False,
        )

    response = client.get("/unit_api/jobs/running")
    assert response.status_code == 200
    rows = response.get_json()
    assert isinstance(rows, list)
    assert [row["job_id"] for row in rows] == [running_job_id]


def test_create_calibration_sets_active_when_requested(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod.tasks, "save_file", lambda *_args, **_kwargs: FakeTaskResult(True))

    response = client.post(
        "/unit_api/calibrations/media_pump",
        json={
            "calibration_data": _build_valid_calibration_yaml("uploaded_active"),
            "set_as_active": True,
        },
    )

    assert response.status_code == 201
    with local_persistent_storage("active_calibrations") as cache:
        assert cache.get("media_pump") == "uploaded_active"


def test_create_calibration_does_not_set_active_by_default(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod.tasks, "save_file", lambda *_args, **_kwargs: FakeTaskResult(True))

    response = client.post(
        "/unit_api/calibrations/media_pump",
        json={"calibration_data": _build_valid_calibration_yaml("uploaded_inactive")},
    )

    assert response.status_code == 201
    with local_persistent_storage("active_calibrations") as cache:
        assert cache.get("media_pump") is None


def test_create_calibration_rejects_non_boolean_set_as_active(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod.tasks, "save_file", lambda *_args, **_kwargs: FakeTaskResult(True))

    response = client.post(
        "/unit_api/calibrations/media_pump",
        json={
            "calibration_data": _build_valid_calibration_yaml("invalid_bool"),
            "set_as_active": "yes",
        },
    )

    assert response.status_code == 400


def test_create_calibration_returns_error_if_save_fails(client, monkeypatch) -> None:
    import pioreactor.web.unit_api as mod

    monkeypatch.setattr(mod.tasks, "save_file", lambda *_args, **_kwargs: FakeTaskResult(False))

    response = client.post(
        "/unit_api/calibrations/media_pump",
        json={
            "calibration_data": _build_valid_calibration_yaml("failed_write"),
            "set_as_active": True,
        },
    )

    assert response.status_code == 500
    with local_persistent_storage("active_calibrations") as cache:
        assert cache.get("media_pump") is None
