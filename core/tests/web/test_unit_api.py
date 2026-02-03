# -*- coding: utf-8 -*-
"""
Additional unit tests for unit_api endpoints.
"""
import pytest


def test_task_results_pending(client) -> None:
    """GET on non-existent task should return pending status."""
    resp = client.get("/unit_api/task_results/does_not_exist")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "pending or not present"


def test_invalid_update_target(client) -> None:
    """Invalid target for system update should return 404."""
    resp = client.post(
        "/unit_api/system/update/invalid",
        json={"args": [], "options": {}, "env": {}},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data.get("error") == "Invalid target"
    error_info = data.get("error_info", {})
    assert error_info.get("status") == 404
    assert error_info.get("cause") == "Invalid target"
    assert isinstance(error_info.get("remediation"), str)


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
    error_info = data.get("error_info", {})
    assert error_info.get("status") == 400
    assert isinstance(error_info.get("remediation"), str)


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


def test_hardware_check_requires_model_payload(client) -> None:
    resp = client.post("/unit_api/hardware/check", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "Missing model_name or model_version"
    error_info = data.get("error_info", {})
    assert error_info.get("status") == 400
    assert "model_name or model_version" in (error_info.get("cause") or "")
    assert isinstance(error_info.get("remediation"), str)


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
