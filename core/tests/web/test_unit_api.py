# -*- coding: utf-8 -*-
"""
Additional unit tests for unit_api endpoints.
"""
from __future__ import annotations

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
    resp = client.patch("/unit_api/system/utc_clock")
    assert resp.status_code == 202


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
    """Versions for app and ui should be returned."""
    r_ui = client.get("/unit_api/versions/ui")
    assert r_ui.status_code == 200
    v_ui = r_ui.get_json()
    assert "version" in v_ui and isinstance(v_ui["version"], str)

    r_app = client.get("/unit_api/versions/app")
    assert r_app.status_code == 200
    v_app = r_app.get_json()
    assert "version" in v_app and isinstance(v_app["version"], str)
