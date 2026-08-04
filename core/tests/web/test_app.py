# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import zipfile
from datetime import datetime
from datetime import UTC
from io import BytesIO
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from huey.exceptions import TaskException
from pioreactor.web.config import huey
from pytest import MonkeyPatch
from tests.utils import FakeMQTTClient
from tests.utils import FakeMQTTMessageInfo

from .conftest import capture_requests
from .test_unit_api import _build_valid_calibration_yaml
from .test_unit_api import FakeTaskResult

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

huey.immediate = True


@pytest.fixture(autouse=True)
def noop_retained_assignment_publish(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("pioreactor.web.api.publish", lambda *_args, **_kwargs: None)


def test_process_delayed_json_response_accepts_created_status() -> None:
    import pioreactor.web.tasks as mod

    class DummyResponse:
        status_code = 201

        def json(self) -> dict[str, str]:
            return {"msg": "Calibration created successfully."}

    assert mod._process_delayed_json_response(
        "unit1", "http://unit.local", DummyResponse(), max_attempts=1, timeout=5.0
    ) == (
        "unit1",
        {"ok": True, "unit": "unit1", "value": {"msg": "Calibration created successfully."}},
    )


def test_latest_experiment_endpoint(client) -> None:
    response = client.get("/api/experiments/latest")

    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp3"
    assert data["description"] == "Third experiment"
    assert data["delta_hours"] > 0
    assert data["worker_count"] == 1
    assert data["tags"] == ["media: Rich media", "organism: Bacteria", "archive", "fermentation", "priority"]


def test_assignment_count(client) -> None:
    response = client.get("/api/experiments/assignment_count")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3
    assert data[0]["worker_count"] == 2
    assert data[0]["experiment"] == "exp1"


def test_get_workers(client) -> None:
    response = client.get("/api/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 4  # We have 4 workers in the sample data
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units
    assert "unit3" in units
    assert "unit4" in units


def test_get_workers_includes_literal_ipv4_addresses(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text(
        "[cluster.addresses]\nunit1=192.168.1.10\nunit2=unit2.local\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))

    response = client.get("/api/workers")

    assert response.status_code == 200
    data = {worker["pioreactor_unit"]: worker for worker in response.get_json()}
    assert data["unit1"]["ipv4_address"] == "192.168.1.10"
    assert data["unit2"]["ipv4_address"] is None


@pytest.mark.parametrize("pioreactor_unit", ["203.0.113.10", "unknown-worker"])
@pytest.mark.parametrize("action", ["reboot", "shutdown"])
def test_system_fanout_rejects_unregistered_unit_targets(
    client: FlaskClient, monkeypatch: MonkeyPatch, pioreactor_unit: str, action: str
) -> None:
    def fail_multicast_post(*_args, **_kwargs) -> None:
        raise AssertionError("invalid unit target should not enqueue multicast work")

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", fail_multicast_post)

    response = client.post(f"/api/units/{pioreactor_unit}/system/{action}")

    assert response.status_code == 400


def test_system_fanout_allows_registered_unit_target(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    class FakeHueyTask:
        id = "fake-task-id"

    captured: dict[str, object] = {}

    def fake_multicast_post(endpoint: str, units: list[str], **_kwargs) -> FakeHueyTask:
        captured["endpoint"] = endpoint
        captured["units"] = units
        return FakeHueyTask()

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", fake_multicast_post)

    response = client.post("/api/units/unit1/system/reboot")

    assert response.status_code == 202
    assert captured["endpoint"] == "/unit_api/system/reboot"
    assert captured["units"] == ["unit1"]


def test_system_fanout_task_result_returns_unit_envelope(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.tasks as tasks

    class DummyUnitResponse:
        status_code = 200
        content = b'{"success": true}'
        body = content

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, bool]:
            return {"success": True}

    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "http://unit.local")
    monkeypatch.setattr(tasks, "post_into", lambda *_args, **_kwargs: DummyUnitResponse())

    response = client.post("/api/units/unit1/system/reboot")

    assert response.status_code == 202
    task_payload = client.get(response.get_json()["result_url_path"]).get_json()
    assert task_payload["status"] == "succeeded"
    assert task_payload["result"] == {
        "unit1": {
            "ok": True,
            "unit": "unit1",
            "value": {"success": True},
        }
    }


def test_config_proxy_rejects_unregistered_unit_target(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    def fail_get_from(*_args, **_kwargs) -> None:
        raise AssertionError("invalid unit target should not be proxied")

    monkeypatch.setattr("pioreactor.web.api.get_from", fail_get_from)

    response = client.get("/api/config/units/203.0.113.10/specific")

    assert response.status_code == 400


def test_calibration_session_proxy_rejects_unregistered_worker_target(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    def fail_post_into(*_args, **_kwargs) -> None:
        raise AssertionError("invalid worker target should not be proxied")

    monkeypatch.setattr("pioreactor.web.api.post_into", fail_post_into)

    response = client.post(
        "/api/workers/203.0.113.10/calibrations/sessions",
        json={"target_device": "stirring", "protocol_name": "dc_based"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize("pioreactor_unit", ["203.0.113.10", "localhost", "unit1.local"])
def test_add_worker_rejects_address_like_names(client: FlaskClient, pioreactor_unit: str) -> None:
    response = client.put("/api/workers", json={"pioreactor_unit": pioreactor_unit})

    assert response.status_code == 400


def test_assign_worker_to_experiment_rejects_unregistered_worker(client: FlaskClient) -> None:
    response = client.put("/api/experiments/exp1/workers", json={"pioreactor_unit": "203.0.113.10"})

    assert response.status_code == 400


def test_discover_workers_endpoint(client, monkeypatch) -> None:
    from pioreactor.utils.networking import DiscoveredWorker

    # Mock network discovery to yield an existing and a new worker
    monkeypatch.setattr(
        "pioreactor.utils.networking.discover_workers_on_network",
        lambda terminate: iter(
            [
                DiscoveredWorker(hostname="unit1", ipv4_address="192.168.1.10"),
                DiscoveredWorker(hostname="new_unit", ipv4_address="192.168.1.11"),
            ]
        ),
    )
    response = client.get("/api/workers/discover")
    assert response.status_code == 200
    data = response.get_json()
    units = [w["pioreactor_unit"] for w in data]
    assert "new_unit" in units
    assert "unit1" not in units


def test_setup_worker_passes_optional_ipv4_address(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeAddWorkerResult:
        def __call__(self, blocking: bool, timeout: float) -> bool:
            return True

    def fake_add_new_pioreactor(
        name: str, version: str, model: str, address: str | None = None
    ) -> FakeAddWorkerResult:
        captured["address"] = address
        return FakeAddWorkerResult()

    monkeypatch.setattr("pioreactor.web.api.tasks.add_new_pioreactor", fake_add_new_pioreactor)

    response = client.post(
        "/api/workers/setup",
        json={
            "name": "new-unit",
            "version": "1.5",
            "model": "pioreactor_40ml",
            "ipv4_address": "192.168.1.22",
        },
    )

    assert response.status_code == 200
    assert captured["address"] == "192.168.1.22"


def test_setup_worker_reports_task_failure_details(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    class FakeAddWorkerResult:
        def __call__(self, blocking: bool, timeout: float) -> bool:
            raise TaskException({"error": "ssh connection refused"})

    def fake_add_new_pioreactor(
        name: str, version: str, model: str, address: str | None = None
    ) -> FakeAddWorkerResult:
        return FakeAddWorkerResult()

    monkeypatch.setattr("pioreactor.web.api.tasks.add_new_pioreactor", fake_add_new_pioreactor)

    response = client.post(
        "/api/workers/setup",
        json={
            "name": "new-unit",
            "version": "1.5",
            "model": "pioreactor_40ml",
        },
    )
    body = response.get_json()

    assert response.status_code == 404
    assert body["error"] == "Failed to add worker new-unit."
    assert body["cause"] == "ssh connection refused"
    assert body["remediation"] == "Check the Pioreactor logs for the full worker setup command output."


@pytest.mark.parametrize("ipv4_address", ["999.1.1.1", "not-an-ip", "2001:db8::1"])
def test_setup_worker_rejects_invalid_ipv4_address(
    client: FlaskClient, monkeypatch: MonkeyPatch, ipv4_address: str
) -> None:
    def fail_add_new_pioreactor(*_args, **_kwargs) -> None:
        raise AssertionError("invalid IPv4 should not enqueue add worker task")

    monkeypatch.setattr("pioreactor.web.api.tasks.add_new_pioreactor", fail_add_new_pioreactor)

    response = client.post(
        "/api/workers/setup",
        json={
            "name": "new-unit",
            "version": "1.5",
            "model": "pioreactor_40ml",
            "ipv4_address": ipv4_address,
        },
    )

    assert response.status_code == 400


def test_get_worker(client) -> None:
    response = client.get("/api/workers/unit1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pioreactor_unit"] == "unit1"
    assert data["is_active"] == 1
    assert data["added_at"] == "2023-10-01T10:00:00Z"


def test_get_experiment_assignment_for_worker(client) -> None:
    response = client.get("/api/workers/unit1/experiment")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp1"


def test_get_workers_for_experiment(client) -> None:
    response = client.get("/api/experiments/exp1/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has two workers assigned
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units


def test_add_worker_to_experiment(client) -> None:
    # Add unit4 to exp1
    response = client.put("/api/experiments/exp1/workers", json={"pioreactor_unit": "unit4"})
    assert response.status_code == 200

    # Verify unit4 is now assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit4" in units


def test_add_worker_to_experiment_publishes_retained_assignment(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    published: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def capture_publish(topic: str, payload: bytes, **kwargs: object) -> None:
        published.append((topic, json.loads(payload), kwargs))

    monkeypatch.setattr("pioreactor.web.api.publish", capture_publish)

    response = client.put("/api/experiments/exp1/workers", json={"pioreactor_unit": "unit4"})

    assert response.status_code == 200
    assert len(published) == 1
    topic, payload, kwargs = published[0]
    assert topic == "pioreactor/unit4/$experiment/assignment"
    assert kwargs == {"retain": True}
    assert payload["pioreactor_unit"] == "unit4"
    assert payload["experiment"] == "exp1"
    assert isinstance(payload["assigned_at"], str)
    assert isinstance(payload["updated_at"], str)


def test_reassign_worker_to_experiment_stops_jobs_from_previous_experiment(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_multicast_post(
        endpoint: str,
        units: list[str],
        json: dict[str, object] | list[dict[str, object] | None] | None = None,
        **_kwargs,
    ) -> dict[str, object]:
        captured["endpoint"] = endpoint
        captured["units"] = units
        captured["json"] = json
        return {}

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", fake_multicast_post)

    response = client.put("/api/experiments/exp2/workers", json={"pioreactor_unit": "unit2"})
    assert response.status_code == 200

    assert captured["endpoint"] == "/unit_api/jobs/stop"
    assert captured["units"] == ["unit2"]
    assert captured["json"] == {"experiment": "exp1"}

    response = client.get("/api/workers/unit2/experiment")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp2"


def test_remove_worker_from_experiment(client) -> None:
    # Remove unit2 from exp1
    response = client.delete("/api/experiments/exp1/workers/unit2")
    assert response.status_code == 200

    # Verify unit2 is no longer assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit2" not in units


def test_all_workers_ever_assigned_to_experiment_includes_unassigned_workers(client) -> None:
    from pioreactor.web.app import get_all_workers_ever_assigned_to_experiment
    from pioreactor.web.app import modify_app_db

    assert set(get_all_workers_ever_assigned_to_experiment("exp1")) == {"unit1", "unit2"}

    response = client.delete("/api/experiments/exp1/workers/unit2")

    assert response.status_code == 200
    modify_app_db(
        """
        INSERT OR IGNORE INTO experiment_worker_assignments_history
            (pioreactor_unit, experiment, assigned_at, unassigned_at)
        VALUES (?, ?, ?, ?)
        """,
        ("unit2", "exp1", "2026-06-01T00:00:00Z", "2026-06-01T01:00:00Z"),
    )
    assert set(get_all_workers_ever_assigned_to_experiment("exp1")) == {"unit1", "unit2"}
    assert set(get_all_workers_ever_assigned_to_experiment("$experiment")) >= {"unit1", "unit2"}


def test_remove_worker_from_experiment_publishes_retained_unassignment(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    published: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def capture_publish(topic: str, payload: bytes, **kwargs: object) -> None:
        published.append((topic, json.loads(payload), kwargs))

    monkeypatch.setattr("pioreactor.web.api.publish", capture_publish)

    response = client.delete("/api/experiments/exp1/workers/unit2")

    assert response.status_code == 200
    assert len(published) == 1
    topic, payload, kwargs = published[0]
    assert topic == "pioreactor/unit2/$experiment/assignment"
    assert kwargs == {"retain": True}
    assert payload["pioreactor_unit"] == "unit2"
    assert payload["experiment"] is None
    assert payload["assigned_at"] is None
    assert isinstance(payload["updated_at"], str)


def test_remove_worker_from_experiment_it_doesnt_belong_to(client) -> None:
    # Try to remove unit2 from an experiment it's not assigned to.
    response = client.delete("/api/experiments/exp99/workers/unit2")
    assert response.status_code == 404


def test_get_assignment_count(client) -> None:
    response = client.get("/api/experiments/assignment_count")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3  # We have 3 experiments
    exp1 = next((item for item in data if item["experiment"] == "exp1"))
    exp2 = next((item for item in data if item["experiment"] == "exp2"))
    exp3 = next((item for item in data if item["experiment"] == "exp3"))
    assert exp1["worker_count"] == 2
    assert exp2["worker_count"] == 1
    assert exp3["worker_count"] == 1


def test_change_worker_status(client) -> None:
    # Deactivate unit3
    response = client.put("/api/workers/unit3/is_active", json={"is_active": 0})
    assert response.status_code == 200

    # Verify the status change
    response = client.get("/api/workers/unit3")
    data = response.get_json()
    assert data["is_active"] == 0


def test_change_worker_model_triggers_hardware_check_for_v1_5(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post_into_unit(unit: str, endpoint: str, json: dict | None = None) -> None:
        captured["unit"] = unit
        captured["endpoint"] = endpoint
        captured["json"] = json

    monkeypatch.setattr("pioreactor.web.api.tasks.post_into_unit", fake_post_into_unit)

    response = client.put(
        "/api/workers/unit1/model",
        json={"model_name": "pioreactor_20ml", "model_version": "1.5"},
    )
    assert response.status_code == 200
    assert captured["unit"] == "unit1"
    assert captured["endpoint"] == "/unit_api/hardware/check"
    assert captured["json"] == {"model_name": "pioreactor_20ml", "model_version": "1.5"}


def test_change_worker_model_triggers_hardware_check_for_non_v1_5(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post_into_unit(unit: str, endpoint: str, json: dict | None = None) -> None:
        captured["unit"] = unit
        captured["endpoint"] = endpoint
        captured["json"] = json

    monkeypatch.setattr("pioreactor.web.api.tasks.post_into_unit", fake_post_into_unit)

    response = client.put(
        "/api/workers/unit1/model",
        json={"model_name": "pioreactor_20ml", "model_version": "1.1"},
    )
    assert response.status_code == 200
    assert captured["unit"] == "unit1"
    assert captured["endpoint"] == "/unit_api/hardware/check"
    assert captured["json"] == {"model_name": "pioreactor_20ml", "model_version": "1.1"}


def test_get_unit_labels(client) -> None:
    response = client.get("/api/experiments/exp1/unit_labels")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has labels for unit1 and unit2
    assert data["unit1"] == "Reactor 1"
    assert data["unit2"] == "Reactor 2"


def test_upsert_unit_labels(client) -> None:
    # Update label for unit1 in exp1
    response = client.patch(
        "/api/experiments/exp1/unit_labels",
        json={"unit": "unit1", "label": "Updated Reactor 1"},
    )
    assert response.status_code == 201

    # Verify the label update
    response = client.get("/api/experiments/exp1/unit_labels")
    data = response.get_json()
    assert data["unit1"] == "Updated Reactor 1"


@pytest.mark.xfail(reason="need to mock datetime")
def test_get_logs_for_unit_and_experiment(client) -> None:
    response = client.get("/api/workers/unit1/experiments/exp1/logs")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1  # Only one log entry for unit1 in exp1
    log = data[0]
    assert log["message"] == "Started mixing"
    assert log["source"] == "mixer"
    assert log["level"] == "INFO"
    assert log["task"] == "mixing_task"


@pytest.mark.xfail(reason="need to mock datetime")
def test_get_growth_rates(client) -> None:
    response = client.get("/api/experiments/exp1/time_series/growth_rates")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # Two growth rates for exp1
    rates = [item["rate"] for item in data]
    assert 0.02 in rates
    assert 0.025 in rates


def test_get_system_logs_filters_universal_experiment(client) -> None:
    from pioreactor.web.app import modify_app_db
    from pioreactor.whoami import UNIVERSAL_EXPERIMENT

    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            UNIVERSAL_EXPERIMENT,
            "unit1",
            "2023-10-04T12:00:00Z",
            "System event logged",
            "system",
            "INFO",
            "system",
        ),
    )

    response = client.get("/api/units/unit1/system_logs")
    assert response.status_code == 200
    data = response.get_json()
    assert any(row["message"] == "System event logged" for row in data)
    assert all(row["experiment"] == UNIVERSAL_EXPERIMENT for row in data)


def test_get_recent_logs_excludes_universal_experiment(client) -> None:
    from pioreactor.web.app import modify_app_db
    from pioreactor.whoami import UNIVERSAL_EXPERIMENT

    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "exp1",
            "unit1",
            now,
            "Experiment-only event",
            "app",
            "INFO",
            "app",
        ),
    )
    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            UNIVERSAL_EXPERIMENT,
            "unit1",
            now,
            "Universal event",
            "app",
            "INFO",
            "app",
        ),
    )

    response = client.get("/api/experiments/exp1/recent_logs")
    assert response.status_code == 200
    data = response.get_json()

    assert any(row["message"] == "Experiment-only event" for row in data)
    assert all(row["message"] != "Universal event" for row in data)
    assert all(row["experiment"] == "exp1" for row in data)


def test_get_experiment_logs_filters_by_min_level_and_orders_by_timestamp(client) -> None:
    from pioreactor.web.app import modify_app_db

    logs = [
        ("2023-10-04T12:00:00Z", "Info event", "INFO"),
        ("2023-10-04T12:01:00Z", "Notice event", "NOTICE"),
        ("2023-10-04T12:02:00Z", "Warning event", "WARNING"),
        ("2023-10-04T12:03:00Z", "Error event", "ERROR"),
    ]
    for timestamp, message, level in logs:
        modify_app_db(
            "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("exp1", "unit1", timestamp, message, "app", level, "app"),
        )

    response = client.get("/api/experiments/exp1/logs?min_level=NOTICE")

    assert response.status_code == 200
    messages = [row["message"] for row in response.get_json()]
    assert messages[:3] == ["Error event", "Warning event", "Notice event"]
    assert "Info event" not in messages


def test_experiment_logs_query_uses_experiment_level_timestamp_index() -> None:
    from pioreactor.web.api import build_experiment_logs_query
    from pioreactor.web.api import get_levels_for_min_level

    levels = get_levels_for_min_level("NOTICE")
    query_args = tuple(arg for level in levels for arg in ("exp1", level)) + (0,)
    db = sqlite3.connect(":memory:")
    db.executescript(
        (Path(__file__).resolve().parents[3] / "packaging/shared-assets/sql/create_tables.sql").read_text()
    )

    plan = db.execute(
        "EXPLAIN QUERY PLAN " + build_experiment_logs_query(levels),
        query_args,
    ).fetchall()

    details = "\n".join(row[3] for row in plan)
    assert "logs_exp_level_timestamp_ix" in details
    assert "logs_exp_timestamp_ix" not in details


@pytest.mark.parametrize(
    "path",
    [
        "/api/experiments/exp1/time_series/temperature_readings",
        "/api/workers/unit1/experiments/exp1/time_series/temperature_readings",
    ],
)
def test_time_series_target_points_validation_returns_400(client, path: str) -> None:
    response = client.get(f"{path}?target_points=0")
    assert response.status_code == 400


def test_time_series_uses_canonical_timestamp_bounds(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    from pioreactor.web.app import modify_app_db

    monkeypatch.setattr(
        "pioreactor.web.api.current_utc_datetime",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    modify_app_db(
        "INSERT INTO experiments (experiment, created_at, description) VALUES (?, ?, ?)",
        ("time-series-bounds-test", "2025-12-31T22:00:00.000Z", ""),
    )

    for timestamp in (
        "2025-12-31T22:00:00.000Z",
        "2025-12-31T23:00:00.000Z",
        "2026-01-01T00:00:00.000Z",
    ):
        modify_app_db(
            """
            INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate)
            VALUES (?, ?, ?, ?)
            """,
            ("time-series-bounds-test", "unit-a", timestamp, 0.1),
        )

    response = client.get(
        "/api/experiments/time-series-bounds-test/time_series/growth_rates" "?lookback=2&target_points=10"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "series": ["unit-a"],
        "data": [
            [
                {"x": "2025-12-31T23:00:00.000Z", "y": 0.1},
                {"x": "2026-01-01T00:00:00.000Z", "y": 0.1},
            ]
        ],
    }


def test_time_series_uses_actual_data_duration_and_requested_point_ceiling(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    from pioreactor.web.app import modify_app_db

    monkeypatch.setattr(
        "pioreactor.web.api.current_utc_datetime",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    modify_app_db(
        "INSERT INTO experiments (experiment, created_at, description) VALUES (?, ?, ?)",
        ("time-series-test", "2025-12-31T12:00:00.000Z", ""),
    )

    for hour in range(12, 23):
        modify_app_db(
            """
            INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate)
            VALUES (?, ?, ?, ?)
            """,
            ("time-series-test", "unit-a", f"2025-12-31T{hour:02}:00:00.000Z", hour / 100),
        )

    for hour in (18, 20, 22):
        modify_app_db(
            """
            INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate)
            VALUES (?, ?, ?, ?)
            """,
            ("time-series-test", "unit-b", f"2025-12-31T{hour:02}:00:00.000Z", hour / 100),
        )

    for timestamp in (
        "2025-12-31T12:00:00.000Z",
        "2025-12-31T12:01:00.000Z",
        "2025-12-31T12:02:00.000Z",
        "2025-12-31T22:00:00.000Z",
        "2025-12-31T22:01:00.000Z",
        "2025-12-31T22:02:00.000Z",
    ):
        modify_app_db(
            """
            INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate)
            VALUES (?, ?, ?, ?)
            """,
            ("time-series-test", "unit-c", timestamp, 0.1),
        )

    response = client.get(
        "/api/experiments/time-series-test/time_series/growth_rates?lookback=20&target_points=4"
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["series"] == ["unit-a", "unit-b", "unit-c"]
    assert [[point["x"] for point in series] for series in data["data"]] == [
        [
            "2025-12-31T12:00:00.000Z",
            "2025-12-31T16:00:00.000Z",
            "2025-12-31T19:00:00.000Z",
            "2025-12-31T22:00:00.000Z",
        ],
        [
            "2025-12-31T18:00:00.000Z",
            "2025-12-31T20:00:00.000Z",
            "2025-12-31T22:00:00.000Z",
        ],
        [
            "2025-12-31T12:00:00.000Z",
            "2025-12-31T22:00:00.000Z",
            "2025-12-31T22:02:00.000Z",
        ],
    ]

    short_lookback_response = client.get(
        "/api/workers/unit-a/experiments/time-series-test/time_series/growth_rates"
        "?lookback=2.5&target_points=4"
    )

    assert short_lookback_response.status_code == 200
    assert short_lookback_response.get_json() == {
        "series": ["unit-a"],
        "data": [[{"x": "2025-12-31T22:00:00.000Z", "y": 0.22}]],
    }

    latest_response = client.get(
        "/api/experiments/time-series-test/time_series/growth_rates?lookback=20&target_points=1"
    )

    assert latest_response.status_code == 200
    assert [[point["x"] for point in series] for series in latest_response.get_json()["data"]] == [
        ["2025-12-31T22:00:00.000Z"],
        ["2025-12-31T22:00:00.000Z"],
        ["2025-12-31T22:02:00.000Z"],
    ]


def test_time_series_partitions_channel_sources(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    from pioreactor.web.app import modify_app_db

    monkeypatch.setattr(
        "pioreactor.web.api.current_utc_datetime",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    modify_app_db(
        "INSERT INTO experiments (experiment, created_at, description) VALUES (?, ?, ?)",
        ("time-series-od-test", "2025-12-31T12:00:00.000Z", ""),
    )

    for channel in (1, 2):
        for hour in range(12, 17):
            modify_app_db(
                """
                INSERT INTO od_readings (
                    experiment, pioreactor_unit, timestamp, od_reading, angle, channel
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "time-series-od-test",
                    "unit-a",
                    f"2025-12-31T{hour:02}:00:00.000Z",
                    channel + hour / 100,
                    90,
                    channel,
                ),
            )

    response = client.get(
        "/api/experiments/time-series-od-test/time_series/od_readings" "?lookback=20&target_points=3"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "series": ["unit-a-1", "unit-a-2"],
        "data": [
            [
                {"x": "2025-12-31T12:00:00.000Z", "y": 1.12},
                {"x": "2025-12-31T14:00:00.000Z", "y": 1.14},
                {"x": "2025-12-31T16:00:00.000Z", "y": 1.16},
            ],
            [
                {"x": "2025-12-31T12:00:00.000Z", "y": 2.12},
                {"x": "2025-12-31T14:00:00.000Z", "y": 2.14},
                {"x": "2025-12-31T16:00:00.000Z", "y": 2.16},
            ],
        ],
    }


@pytest.mark.parametrize(
    ("route", "insert_statement", "insert_args", "expected_series", "expected_y"),
    [
        (
            "growth_rates",
            """
            INSERT INTO growth_rates (experiment, pioreactor_unit, timestamp, rate)
            VALUES (?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 0.1234567),
            "unit-a",
            0.12346,
        ),
        (
            "temperature_readings",
            """
            INSERT INTO temperature_readings (
                experiment, pioreactor_unit, timestamp, temperature_c
            )
            VALUES (?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 20.126),
            "unit-a",
            20.13,
        ),
        (
            "od_readings_filtered",
            """
            INSERT INTO od_readings_filtered (
                experiment, pioreactor_unit, timestamp, normalized_od_reading
            )
            VALUES (?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 0.123456789),
            "unit-a",
            0.1234568,
        ),
        (
            "od_readings",
            """
            INSERT INTO od_readings (
                experiment, pioreactor_unit, timestamp, od_reading, angle, channel
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 0.123456789, 90, 1),
            "unit-a-1",
            0.1234568,
        ),
        (
            "od_readings_fused",
            """
            INSERT INTO od_readings_fused (experiment, pioreactor_unit, timestamp, od_reading)
            VALUES (?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 0.123456789),
            "unit-a",
            0.1234568,
        ),
        (
            "raw_od_readings",
            """
            INSERT INTO raw_od_readings (
                experiment, pioreactor_unit, timestamp, od_reading, channel
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("source-test", "unit-a", "2025-12-31T22:00:00.000Z", 0.123456789, 1),
            "unit-a-1",
            0.1234568,
        ),
    ],
)
def test_built_in_time_series_source_configuration(
    client: FlaskClient,
    monkeypatch: MonkeyPatch,
    route: str,
    insert_statement: str,
    insert_args: tuple[object, ...],
    expected_series: str,
    expected_y: float,
) -> None:
    from pioreactor.web.app import modify_app_db

    monkeypatch.setattr(
        "pioreactor.web.api.current_utc_datetime",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    modify_app_db(
        "INSERT INTO experiments (experiment, created_at, description) VALUES (?, ?, ?)",
        ("source-test", "2025-12-31T12:00:00.000Z", ""),
    )
    modify_app_db(insert_statement, insert_args)

    response = client.get(f"/api/experiments/source-test/time_series/{route}?lookback=20&target_points=3")

    assert response.status_code == 200
    assert response.get_json() == {
        "series": [expected_series],
        "data": [[{"x": "2025-12-31T22:00:00.000Z", "y": expected_y}]],
    }


def test_create_experiment(client) -> None:
    # Create a new experiment
    response = client.post(
        "/api/experiments",
        json={
            "experiment": "exp4",
            "created_at": "2023-10-04T12:00:00Z",
            "description": "Fourth experiment",
            "tags": ["seed", "project-x", "seed"],
            "delta_hours": 0,
            "worker_count": 0,
        },
    )
    assert response.status_code == 201  # Created
    data = response.get_json()
    assert data["tags"] == ["seed", "project-x"]

    # Verify the experiment exists
    response = client.get("/api/experiments/exp4")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp4"
    assert data["description"] == "Fourth experiment"
    assert data["tags"] == ["seed", "project-x"]
    assert data["worker_count"] == 0


@pytest.mark.parametrize("description_payload", [None, "omitted"])
def test_create_experiment_normalizes_missing_description_to_empty_string(
    client, description_payload: str | None
) -> None:
    payload: dict[str, object] = {"experiment": f"exp-with-{description_payload}-description"}
    if description_payload != "omitted":
        payload["description"] = description_payload

    response = client.post("/api/experiments", json=payload)

    assert response.status_code == 201
    assert response.get_json()["description"] == ""


def test_create_duplicate_experiment(client) -> None:
    # Try to create an experiment with a duplicate name 'exp1'
    response = client.post(
        "/api/experiments",
        json={
            "experiment": "exp1",
            "description": "Duplicate experiment",
        },
    )
    assert response.status_code == 409


def test_delete_experiment_endpoint_schedules_task(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as api

    class DummyTask:
        id = "delete-experiment-task"

    captured: dict[str, object] = {}

    def fake_delete_experiment_task(experiment: str, units: list[str]) -> DummyTask:
        captured["experiment"] = experiment
        captured["units"] = units
        return DummyTask()

    monkeypatch.setattr(api.tasks, "delete_experiment_task", fake_delete_experiment_task)
    monkeypatch.setattr(
        api.fanout,
        "broadcast_post_across_cluster",
        lambda endpoint, json=None: captured.update({"endpoint": endpoint, "json": json}),
    )

    response = client.delete("/api/experiments/exp1")

    assert response.status_code == 202
    assert response.get_json()["task_id"] == "delete-experiment-task"
    assert captured == {
        "experiment": "exp1",
        "units": ["unit1", "unit2"],
        "endpoint": "/unit_api/jobs/stop",
        "json": {"experiment": "exp1"},
    }


def test_delete_experiment_endpoint_returns_404_without_scheduling_task(
    client, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as api

    def fail_delete_experiment_task(experiment: str, units: list[str]) -> None:
        raise AssertionError("delete task should not be scheduled")

    monkeypatch.setattr(api.tasks, "delete_experiment_task", fail_delete_experiment_task)
    monkeypatch.setattr(
        api.fanout,
        "broadcast_post_across_cluster",
        lambda endpoint, json=None: (_ for _ in ()).throw(
            AssertionError("stop fanout should not be scheduled")
        ),
    )

    response = client.delete("/api/experiments/not-real")

    assert response.status_code == 404


def test_update_experiment(client) -> None:
    # Update an existing experiment
    response = client.patch(
        "/api/experiments/exp2",
        json={
            "description": "Updated second experiment",
            "tags": ["project-beta", "  follow-up ", "PROJECT-BETA", ""],
        },
    )
    assert response.status_code == 200  # OK
    data = response.get_json()
    assert data["tags"] == ["project-beta", "follow-up"]

    # Verify the updates
    response = client.get("/api/experiments/exp2")
    data = response.get_json()
    assert data["description"] == "Updated second experiment"
    assert data["tags"] == ["project-beta", "follow-up"]


def test_get_experiments_includes_tags_and_worker_count(client) -> None:
    response = client.get("/api/experiments")

    assert response.status_code == 200
    data = response.get_json()
    exp3 = next(item for item in data if item["experiment"] == "exp3")
    exp0 = next(item for item in data if item["experiment"] == "exp0")
    assert exp3["worker_count"] == 1
    assert exp3["tags"] == ["media: Rich media", "organism: Bacteria", "archive", "fermentation", "priority"]
    assert exp0["worker_count"] == 0
    assert exp0["tags"] == []


def test_update_experiment_tags_only(client) -> None:
    response = client.patch(
        "/api/experiments/exp1",
        json={
            "tags": ["RNA", "screening", "rna", "scale-up"],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["description"] == "First experiment"
    assert data["tags"] == ["RNA", "screening", "scale-up"]


def test_update_nonexistent_experiment(client) -> None:
    # Try to update an experiment that doesn't exist
    response = client.patch(
        "/api/experiments/nonexistent_exp",
        json={
            "description": "This should fail",
        },
    )
    assert response.status_code == 404  # Not Found


def test_update_experiment_with_invalid_tags_payload(client) -> None:
    response = client.patch(
        "/api/experiments/exp1",
        json={
            "tags": "project-a",
        },
    )

    assert response.status_code == 400


def test_update_experiment_can_clear_description(client) -> None:
    response = client.patch(
        "/api/experiments/exp1",
        json={"description": None},
    )

    assert response.status_code == 200
    assert response.get_json()["description"] == ""


def test_update_experiment_requires_a_supported_field(client) -> None:
    response = client.patch("/api/experiments/exp1", json={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing description or tags"


def test_create_experiment_missing_fields(client) -> None:
    # Try to create an experiment without required fields
    response = client.post(
        "/api/experiments",
        json={
            # Missing 'experiment' name
            "description": "No name experiment",
        },
    )
    assert response.status_code == 400  # Bad Request


@pytest.mark.parametrize(
    ("experiment_name", "expected_error"),
    [
        ("current", "Experiment name cannot be 'current'"),
        ("_testing_exp", "Experiment name cannot start with '_testing'"),
        (
            "bad/name",
            "Experiment name cannot contain special characters (#, $, %, +, /, ?, \\)",
        ),
        (
            "bad?name",
            "Experiment name cannot contain special characters (#, $, %, +, /, ?, \\)",
        ),
        (["exp4"], "Invalid request body."),
    ],
)
def test_create_experiment_rejects_invalid_names(
    client: FlaskClient, experiment_name: object, expected_error: str
) -> None:
    response = client.post("/api/experiments", json={"experiment": experiment_name})

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error


@pytest.mark.parametrize("experiment_name", ["condition A&B", "condition=A"])
def test_experiment_names_keep_non_delimiting_url_characters(experiment_name: str) -> None:
    import pioreactor.web.api as mod

    assert mod._validate_experiment_name(experiment_name) == experiment_name


def test_404_for_unknown_api(client) -> None:
    response = client.get("/api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/unit_api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/this-doesnt-exist")
    assert response.status_code == 404


def test_removed_config_files_api_returns_404(client) -> None:
    response = client.get("/api/config/files/not-a-config.txt")
    assert response.status_code == 404


def test_get_config_for_broadcast_uses_worker_merged_config(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from pioreactor.web.app import HOSTNAME

    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text(
        "[cluster.topology]\nleader_hostname=leader\nleader_address=leader.local\n[mqtt]\nbroker_address=leader.local\n[shared]\nvalue=global\n",
        encoding="utf-8",
    )
    (dot_pioreactor / "unit_config.ini").write_text("[shared]\nvalue=leader\n", encoding="utf-8")

    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    monkeypatch.setattr("pioreactor.web.api.get_all_units", lambda: [HOSTNAME, "unit1", "unit2"])
    monkeypatch.setattr(
        "pioreactor.web.cache.multicast_get_with_leader_cache",
        lambda *_args, **_kwargs: {
            "unit1": {"ok": True, "unit": "unit1", "value": {"shared": {"value": "unit1"}}},
            "unit2": {
                "ok": False,
                "unit": "unit2",
                "error": {
                    "kind": "connection_error",
                    "message": "Could not reach unit2.",
                    "remediation": "Check that unit2 is online and retry.",
                },
                "status_code": None,
                "retryable": True,
            },
        },
    )
    response = client.get("/api/config/units/$broadcast")
    assert response.status_code == 200

    data = response.get_json()
    assert data["configs"][HOSTNAME]["shared"]["value"] == "leader"
    assert data["configs"]["unit1"]["shared"]["value"] == "unit1"
    assert data["errors"]["unit2"] == {
        "ok": False,
        "unit": "unit2",
        "error": {
            "kind": "connection_error",
            "message": "Could not reach unit2.",
            "remediation": "Check that unit2 is online and retry.",
        },
        "status_code": None,
        "retryable": True,
    }


def test_get_config_for_worker_unwraps_merged_config(client: FlaskClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pioreactor.web.cache.multicast_get_with_leader_cache",
        lambda *_args, **_kwargs: {
            "unit1": {"ok": True, "unit": "unit1", "value": {"shared": {"value": "unit1"}}},
        },
    )

    response = client.get("/api/config/units/unit1")

    assert response.status_code == 200
    assert response.get_json() == {
        "configs": {"unit1": {"shared": {"value": "unit1"}}},
        "errors": {},
    }


@pytest.mark.parametrize(
    ("worker_status_code", "expected_status_code"), [(None, 502), (200, 502), (400, 400)]
)
def test_get_config_for_worker_surfaces_merged_config_failure(
    client: FlaskClient, monkeypatch: MonkeyPatch, worker_status_code: int | None, expected_status_code: int
) -> None:
    monkeypatch.setattr(
        "pioreactor.web.cache.multicast_get_with_leader_cache",
        lambda *_args, **_kwargs: {
            "unit1": {
                "ok": False,
                "unit": "unit1",
                "error": {
                    "kind": "connection_error",
                    "message": "Could not reach unit1.",
                    "remediation": "Check that unit1 is online and retry.",
                },
                "status_code": worker_status_code,
                "retryable": True,
            },
        },
    )

    response = client.get("/api/config/units/unit1")

    assert response.status_code == expected_status_code
    assert response.get_json() == {
        "error": "Could not reach unit1.",
        "status": expected_status_code,
        "cause": "Could not reach unit1.",
        "remediation": "Check that unit1 is online and retry.",
    }


def test_unit_api_specific_config_round_trip(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text(
        "[cluster.topology]\nleader_hostname=leader\nleader_address=leader.local\n[mqtt]\nbroker_address=leader.local\n[shared]\nvalue=global\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))

    response = client.get("/unit_api/config/specific")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == ""

    response = client.patch("/unit_api/config/specific", json={"code": "[shared]\nvalue=unit-local\n"})
    assert response.status_code == 200

    response = client.get("/unit_api/config/specific")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == "[shared]\nvalue=unit-local\n"

    response = client.get("/unit_api/config/merged")
    assert response.status_code == 200
    assert response.get_json()["shared"]["value"] == "unit-local"


def test_update_specific_config_for_worker_saves_snapshot(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "post_into",
        lambda *_args, **_kwargs: MureqResponse(
            "http://unit1.local:4999/unit_api/config/specific",
            200,
            {"Content-Type": "application/json"},
            b'{"status":"success"}',
        ),
    )

    response = client.patch("/api/config/units/unit1/specific", json={"code": "[section]\nvalue=1\n"})
    assert response.status_code == 200

    history_response = client.get("/api/config/units/unit1/specific/history")
    assert history_response.status_code == 200
    history = history_response.get_json()
    assert history[0]["filename"] == "unit_config.ini::unit1"
    assert history[0]["data"] == "[section]\nvalue=1\n"


def test_config_history_responses_require_revalidation(client: FlaskClient) -> None:
    for endpoint in ("/api/config/shared/history", "/api/config/units/unit1/specific/history"):
        response = client.get(endpoint)

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=0"


def test_zipped_configs_contains_shared_and_all_reachable_unit_configs(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text("[shared]\nvalue=global\n", encoding="utf-8")
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))

    class FakeTask:
        def get(self, blocking: bool, timeout: float) -> dict[str, object]:
            return {
                "unit1": {
                    "ok": True,
                    "unit": "unit1",
                    "value": b"[unit]\nvalue=one\n",
                },
                "unit2": {
                    "ok": True,
                    "unit": "unit2",
                    "value": None,
                },
                "unit3": {
                    "ok": False,
                    "unit": "unit3",
                    "error": {"kind": "connection_error", "message": "Could not reach unit3."},
                    "status_code": None,
                    "retryable": True,
                },
            }

    monkeypatch.setattr(
        "pioreactor.web.api.fanout.broadcast_get_across_cluster",
        lambda *args, **kwargs: FakeTask(),
    )
    monkeypatch.setattr(
        "pioreactor.web.api.current_utc_timestamp",
        lambda: "2026-07-29T14:32:10.000Z",
    )

    response = client.get("/api/config/zipped")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == "attachment; filename=configuration_inis.zip"
    with zipfile.ZipFile(BytesIO(response.data), "r") as zf:
        assert zf.namelist() == [
            "config.ini",
            "unit1/unit_config.ini",
            "unit2/unit_config.ini",
            "metadata.json",
        ]
        assert zf.read("config.ini") == b"[shared]\nvalue=global\n"
        assert zf.read("unit1/unit_config.ini") == b"[unit]\nvalue=one\n"
        assert zf.read("unit2/unit_config.ini") == b""
        assert json.loads(zf.read("metadata.json")) == {
            "metadata_version": 1,
            "downloaded_at_utc": "2026-07-29T14:32:10.000Z",
            "included_config_files": [
                "config.ini",
                "unit1/unit_config.ini",
                "unit2/unit_config.ini",
            ],
            "omitted_units": ["unit3"],
        }


def test_update_specific_config_for_worker_propagates_validation_error(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "post_into",
        lambda *_args, **_kwargs: MureqResponse(
            "http://unit1.local:4999/unit_api/config/specific",
            400,
            {"Content-Type": "application/json"},
            (
                b'{"error":"Incorrect syntax. Please fix and try again.",'
                b'"status":400,'
                b'"cause":"The INI text could not be parsed.",'
                b'"remediation":"Fix the INI syntax and retry."}'
            ),
        ),
    )

    response = client.patch("/api/config/units/unit1/specific", json={"code": "[broken"})
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Incorrect syntax. Please fix and try again.",
        "status": 400,
        "cause": "The INI text could not be parsed.",
        "remediation": "Fix the INI syntax and retry.",
    }


def test_update_specific_config_for_worker_rejects_unstructured_worker_error(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "post_into",
        lambda *_args, **_kwargs: MureqResponse(
            "http://unit1.local:4999/unit_api/config/specific",
            400,
            {"Content-Type": "application/json"},
            b'{"error":"legacy worker error"}',
        ),
    )

    response = client.patch("/api/config/units/unit1/specific", json={"code": "[broken"})

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "Updating unit-specific config failed on unit1. (HTTP 400).",
        "status": 502,
        "cause": "The worker returned an invalid error response.",
        "remediation": "Check the worker logs and retry.",
    }


def test_create_experiment_profile_invalid_filename_returns_400(client) -> None:
    response = client.post(
        "/api/experiment_profiles",
        json={"body": 'version: "1.0"\nexperiment_profile_name: demo', "filename": "bad?name.yaml"},
    )
    assert response.status_code == 400


def test_update_experiment_profile_invalid_filename_returns_400(client) -> None:
    response = client.patch(
        "/api/experiment_profiles/bad:name.yaml",
        json={"body": 'version: "1.0"\nexperiment_profile_name: demo'},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/experiment_profiles", {}),
        ("patch", "/api/experiment_profiles/demo.yaml", {}),
        ("patch", "/api/config/shared", {}),
        ("post", "/api/datasets/exportable/export", {}),
        ("post", "/api/datasets/exportable/export-to-usb", {}),
        ("patch", "/api/workers/unit1/jobs/update/job_name/stirring/experiments/exp1", {}),
        ("patch", "/api/workers/unit1/bioreactor/update/experiments/exp1", {}),
        ("post", "/api/system/utc_clock", {}),
        ("post", "/api/workers/unit1/experiments/exp1/logs", {}),
        ("post", "/api/workers/unit1/calibrations/media_pump", {}),
        ("post", "/api/units/unit1/plugins/install-from-leader-usb", {}),
        ("post", "/api/system/update_from_archive", {}),
        ("post", "/api/workers/unit1/calibrations/sessions", {}),
        ("patch", "/api/config/units/unit1/specific", {}),
        ("post", "/api/experiments", {}),
        ("put", "/api/experiments/exp1/unit_labels", {}),
        ("post", "/api/workers/setup", {}),
        ("put", "/api/workers", {}),
        ("put", "/api/workers/unit1/is_active", {}),
        ("put", "/api/workers/unit1/model", {}),
        ("put", "/api/experiments/exp1/workers", {}),
    ],
)
def test_mutation_routes_reject_missing_required_json_fields(
    client: FlaskClient, method: str, path: str, payload: dict[str, object]
) -> None:
    response = client.open(path, method=method, json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."
    assert response.get_json()["status"] == 400


def test_export_datasets_rejects_malformed_json(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        data=b"{",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_export_datasets_rejects_wrong_field_types(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": "od_readings",
            "experiment": "exp1",
            "partition_by_unit": True,
            "partition_by_experiment": False,
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Invalid request body.",
        "status": 400,
        "cause": "Expected `array`, got `str` - at `$.datasets`",
        "remediation": (
            "Send a JSON object with the required fields: datasets, experiment, "
            "partition_by_unit, partition_by_experiment."
        ),
    }


def test_export_datasets_rejects_plural_experiments_field(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": ["od_readings"],
            "experiments": ["exp1"],
            "partition_by_unit": True,
            "partition_by_experiment": False,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_export_datasets_rejects_empty_experiment(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": ["od_readings"],
            "experiment": "",
            "partition_by_unit": True,
            "partition_by_experiment": False,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_create_experiment_profile_returns_diagnostics_for_semantic_validation_errors(client) -> None:
    response = client.post(
        "/api/experiment_profiles",
        json={
            "body": """
version: "1.0"
experiment_profile_name: demo
common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 1.0
          t: 1h
""",
            "filename": "validator_semantic_error_test.yaml",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Validation error."
    assert payload["diagnostics"][0]["code"] == "action.time.conflict"
    assert payload["diagnostics"][0]["path"] == "common.jobs.stirring.actions[0]"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/experiment_profiles"),
        ("patch", "/api/experiment_profiles/validator_expression_error_test.yaml"),
    ],
)
def test_experiment_profile_mutations_reject_incomplete_expressions(
    client: FlaskClient, method: str, path: str
) -> None:
    payload = {
        "body": """
version: "1.0"
experiment_profile_name: demo
common:
  jobs:
    stirring:
      actions:
        - type: start
          t: 0s
          if: 1 +
"""
    }
    if method == "post":
        payload["filename"] = "validator_expression_error_test.yaml"

    response = client.open(
        path,
        method=method,
        json=payload,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Validation error."
    assert payload["diagnostics"][0]["code"] == "expression.syntax"
    assert payload["diagnostics"][0]["path"] == "common.jobs.stirring.actions[0].if"


def test_create_experiment_profile_reports_save_failure(client, monkeypatch) -> None:
    monkeypatch.setattr("pioreactor.web.api.tasks.save_file", lambda *_args, **_kwargs: FakeTaskResult(False))

    response = client.post(
        "/api/experiment_profiles",
        json={
            "body": 'version: "1.0"\nexperiment_profile_name: save_failure_demo',
            "filename": "save_failure_demo.yaml",
        },
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "Failed to save experiment profile."


def test_update_experiment_profile_reports_save_failure(client, monkeypatch) -> None:
    monkeypatch.setattr("pioreactor.web.api.tasks.save_file", lambda *_args, **_kwargs: FakeTaskResult(False))

    response = client.patch(
        "/api/experiment_profiles/save_failure_demo.yaml",
        json={"body": 'version: "1.0"\nexperiment_profile_name: save_failure_demo'},
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "Failed to save experiment profile."


def test_delete_experiment_profile_reports_delete_failure(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    profiles_dir = tmp_path / "experiment_profiles"
    profiles_dir.mkdir()
    (profiles_dir / "delete_failure_demo.yaml").write_text(
        'version: "1.0"\nexperiment_profile_name: delete_failure_demo', encoding="utf-8"
    )
    monkeypatch.setenv("DOT_PIOREACTOR", tmp_path.as_posix())
    monkeypatch.setattr("pioreactor.web.api.tasks.rm", lambda *_args, **_kwargs: FakeTaskResult(False))

    response = client.delete("/api/experiment_profiles/delete_failure_demo.yaml")

    assert response.status_code == 500
    assert response.get_json()["error"] == "Failed to delete experiment profile."


def test_broadcasting(client) -> None:
    response = client.get("/api/workers")
    data = response.get_json()
    count_of_workers = len(data)

    with capture_requests() as bucket:
        response = client.get("/api/units/$broadcast/versions/app")

    assert len(bucket) == (count_of_workers + 1)  # leader is localhost, whos not a worker in this fixture


def test_broadcast_in_manage_all(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 2
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
        },
    }

    # Remove unit2 from exp1
    client.delete("/api/experiments/exp1/workers/unit2")

    with capture_requests() as bucket:
        client.post("/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1", json={})
    assert len(bucket) == 1


def test_get_camera_statuses_for_experiment_uses_historical_experiment_assignments(
    client, monkeypatch: MonkeyPatch
) -> None:
    from pioreactor.mureq import _prepare_request
    from pioreactor.pubsub import create_webserver_path

    class FakeTaskResult:
        def get(self, blocking: bool, timeout: float) -> dict[str, dict]:
            return {
                "unit1": {
                    "ok": True,
                    "unit": "unit1",
                    "value": {"available": True, "latest_still": None},
                },
                "unit2": {
                    "ok": True,
                    "unit": "unit2",
                    "value": {"available": False, "latest_still": None},
                },
            }

    captured: dict[str, object] = {}

    def fake_broadcast_get_across_workers_ever_assigned_to_experiment(
        endpoint: str, experiment: str, timeout: float
    ) -> FakeTaskResult:
        _, connection, path = _prepare_request("GET", create_webserver_path("unit1.local", endpoint))
        connection.close()
        captured["endpoint"] = endpoint
        captured["experiment"] = experiment
        captured["path"] = path
        captured["timeout"] = timeout
        return FakeTaskResult()

    monkeypatch.setattr(
        "pioreactor.web.api.fanout.broadcast_get_across_workers_ever_assigned_to_experiment",
        fake_broadcast_get_across_workers_ever_assigned_to_experiment,
    )

    response = client.get("/api/experiments/experiment%20a/cameras")

    assert response.status_code == 200
    assert captured == {
        "endpoint": "/unit_api/camera/experiments/experiment a/status",
        "experiment": "experiment a",
        "path": "/unit_api/camera/experiments/experiment%20a/status",
        "timeout": 5,
    }
    assert set(response.get_json()["cameras"]) == {"unit1", "unit2"}


def test_unscoped_camera_status_proxy_is_not_available(client) -> None:
    assert client.get("/api/workers/unit1/camera/status").status_code == 404


def test_update_camera_settings_proxy_forwards_to_one_worker(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod

    captured: dict[str, object] = {}

    class DummyTask:
        id = "camera-settings-task"

    def fake_multicast_patch_to_worker(unit: str, endpoint: str, **kwargs: object) -> DummyTask:
        captured["unit"] = unit
        captured["endpoint"] = endpoint
        captured.update(kwargs)
        return DummyTask()

    monkeypatch.setattr(mod, "multicast_patch_to_worker", fake_multicast_patch_to_worker)

    response = client.patch(
        "/api/workers/unit1/camera/settings",
        json={"auto_capture_enabled": False},
    )

    assert response.status_code == 202
    assert response.get_json()["result_url_path"] == "/unit_api/task_results/camera-settings-task"
    assert captured == {
        "unit": "unit1",
        "endpoint": "/unit_api/camera/settings",
        "json": {"auto_capture_enabled": False},
    }


def test_experiment_camera_status_proxy_fetches_worker_experiment_status(
    client, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    captured: dict[str, str] = {}

    def fake_get_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        captured["address"] = address
        captured["endpoint"] = endpoint
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "application/json"},
            b'{"unit":"unit1","available":true,"latest_still":null}',
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "get_from", fake_get_from)

    response = client.get("/api/workers/unit1/camera/experiments/experiment%20a/status")

    assert response.status_code == 200
    assert response.get_json()["unit"] == "unit1"
    assert captured == {
        "address": "unit1.local",
        "endpoint": "/unit_api/camera/experiments/experiment a/status",
    }


def test_unscoped_latest_camera_still_proxy_is_not_available(client) -> None:
    assert client.get("/api/workers/unit1/camera/latest.jpg").status_code == 404


def test_camera_focus_preview_proxy_preserves_image_content_type(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    captured: dict[str, str] = {}

    def fake_get_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        captured["address"] = address
        captured["endpoint"] = endpoint
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "image/jpeg"},
            b"focus preview",
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "get_from", fake_get_from)

    response = client.get("/api/workers/unit1/camera/focus_sessions/session-a/preview.jpg?v=2")

    assert response.status_code == 200
    assert response.data == b"focus preview"
    assert response.content_type == "image/jpeg"
    assert captured == {
        "address": "unit1.local",
        "endpoint": "/unit_api/camera/focus_sessions/session-a/preview.jpg",
    }


def test_camera_stills_proxy_fetches_worker_experiment_stills(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import _prepare_request
    from pioreactor.mureq import Response as MureqResponse
    from pioreactor.pubsub import create_webserver_path

    captured: dict[str, str] = {}

    def fake_get_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        _, connection, path = _prepare_request("GET", create_webserver_path(address, endpoint))
        connection.close()
        captured["address"] = address
        captured["endpoint"] = endpoint
        captured["path"] = path
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "application/json"},
            b'{"unit":"unit1","experiment":"experiment a","stills":[]}',
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "get_from", fake_get_from)

    response = client.get("/api/workers/unit1/camera/experiments/experiment%20a/stills")

    assert response.status_code == 200
    assert response.get_json() == {"unit": "unit1", "experiment": "experiment a", "stills": []}
    assert captured == {
        "address": "unit1.local",
        "endpoint": "/unit_api/camera/experiments/experiment a/stills",
        "path": "/unit_api/camera/experiments/experiment%20a/stills",
    }


def test_capture_camera_still_proxy_posts_to_worker_experiment_stills(
    client, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod

    captured: dict[str, str] = {}

    class DummyTask:
        id = "camera-capture-proxy-task"

    def fake_multicast_post_to_worker(unit: str, endpoint: str) -> DummyTask:
        captured["unit"] = unit
        captured["endpoint"] = endpoint
        return DummyTask()

    monkeypatch.setattr(mod, "multicast_post_to_worker", fake_multicast_post_to_worker)

    response = client.post("/api/workers/unit1/camera/experiments/experiment%20a/stills")

    assert response.status_code == 202
    assert response.get_json()["result_url_path"] == "/unit_api/task_results/camera-capture-proxy-task"
    assert captured == {
        "unit": "unit1",
        "endpoint": "/unit_api/camera/experiments/experiment a/stills",
    }


def test_camera_still_proxy_preserves_image_content_type(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import _prepare_request
    from pioreactor.mureq import Response as MureqResponse
    from pioreactor.pubsub import create_webserver_path

    captured: dict[str, str] = {}

    def fake_get_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        _, connection, path = _prepare_request("GET", create_webserver_path(address, endpoint))
        connection.close()
        captured["address"] = address
        captured["endpoint"] = endpoint
        captured["path"] = path
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "image/jpeg"},
            b"fake jpeg",
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "get_from", fake_get_from)

    response = client.get("/api/workers/unit1/camera/experiments/experiment%20a/stills/image%201.jpg")

    assert response.status_code == 200
    assert response.data == b"fake jpeg"
    assert response.content_type == "image/jpeg"
    assert captured == {
        "address": "unit1.local",
        "endpoint": "/unit_api/camera/experiments/experiment a/stills/image 1.jpg",
        "path": "/unit_api/camera/experiments/experiment%20a/stills/image%201.jpg",
    }


def test_delete_camera_still_proxy_forwards_to_worker(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import _prepare_request
    from pioreactor.mureq import Response as MureqResponse
    from pioreactor.pubsub import create_webserver_path

    captured: dict[str, str] = {}

    def fake_delete_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        _, connection, path = _prepare_request("DELETE", create_webserver_path(address, endpoint))
        connection.close()
        captured["address"] = address
        captured["endpoint"] = endpoint
        captured["path"] = path
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "application/json"},
            b'{"image_id":"image-1"}',
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "delete_from", fake_delete_from)

    response = client.delete("/api/workers/unit1/camera/experiments/experiment%20a/stills/image%201.jpg")

    assert response.status_code == 200
    assert response.get_json() == {"image_id": "image-1"}
    assert captured == {
        "address": "unit1.local",
        "endpoint": "/unit_api/camera/experiments/experiment a/stills/image 1.jpg",
        "path": "/unit_api/camera/experiments/experiment%20a/stills/image%201.jpg",
    }


def test_zipped_camera_stills_proxy_preserves_zip_content_type(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from http.client import HTTPMessage
    from pioreactor.mureq import _prepare_request

    captured: dict[str, object] = {"context_closed": False, "read_sizes": []}

    class FakeStreamingResponse:
        url = "http://unit1.local/unit_api/camera/experiments/experiment%20a/stills.zip"
        status = 200
        headers = HTTPMessage()
        chunks = iter((b"fake ", b"zip", b""))

        def read(self, size: int) -> bytes:
            captured["read_sizes"].append(size)
            return next(self.chunks)

    class FakeStreamingResponseContext:
        def __enter__(self) -> FakeStreamingResponse:
            return FakeStreamingResponse()

        def __exit__(self, *_args: object) -> None:
            captured["context_closed"] = True
            return None

    FakeStreamingResponse.headers["Content-Type"] = "application/zip"
    FakeStreamingResponse.headers["Content-Length"] = "8"
    FakeStreamingResponse.headers["Content-Disposition"] = 'attachment; filename="worker.zip"'

    def fake_yield_response(method: str, url: str, **kwargs: object) -> FakeStreamingResponseContext:
        _, connection, path = _prepare_request(method, url)
        connection.close()
        captured["path"] = path
        captured["timeout"] = kwargs["timeout"]
        return FakeStreamingResponseContext()

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "yield_response", fake_yield_response)

    response = client.get("/api/workers/unit1/camera/experiments/experiment%20a/stills.zip")

    assert response.status_code == 200
    assert response.is_streamed
    assert response.data == b"fake zip"
    assert response.content_type == "application/zip"
    assert response.headers["Content-Length"] == "8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="worker.zip"'
    assert captured == {
        "context_closed": True,
        "path": "/unit_api/camera/experiments/experiment%20a/stills.zip",
        "read_sizes": [64 * 1024, 64 * 1024, 64 * 1024],
        "timeout": 60,
    }


def test_zipped_camera_stills_proxy_preserves_worker_error_details(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from http.client import HTTPMessage

    class FakeErrorResponse:
        url = "http://unit1.local/unit_api/camera/experiments/experiment-a/stills.zip"
        status = 503
        headers = HTTPMessage()

        def read(self, size: int) -> bytes:
            assert size == 1_048_576
            return (
                b'{"error":"Camera archive unavailable.","status":503,'
                b'"cause":"The worker ran out of temporary storage.",'
                b'"remediation":"Free storage on the worker and retry."}'
            )

    class FakeErrorResponseContext:
        def __enter__(self) -> FakeErrorResponse:
            return FakeErrorResponse()

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "yield_response",
        lambda *_args, **_kwargs: FakeErrorResponseContext(),
    )

    response = client.get("/api/workers/unit1/camera/experiments/experiment-a/stills.zip")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "Camera archive unavailable.",
        "status": 503,
        "cause": "The worker ran out of temporary storage.",
        "remediation": "Free storage on the worker and retry.",
    }


def test_camera_capture_proxy_is_not_available(client) -> None:
    assert client.post("/api/workers/unit1/camera/capture", json={}).status_code == 404


def test_task_result_proxy_fetches_worker_task_result(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    captured: dict[str, str] = {}

    def fake_get_from(address: str, endpoint: str, **kwargs: object) -> MureqResponse:
        captured["address"] = address
        captured["endpoint"] = endpoint
        return MureqResponse(
            f"http://{address}{endpoint}",
            200,
            {"Content-Type": "application/json"},
            b'{"status":"succeeded","result":{"image_id":"image-1"}}',
        )

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(mod, "get_from", fake_get_from)

    response = client.get("/api/workers/unit1/task_results/task-1")

    assert response.status_code == 200
    assert response.get_json()["result"]["image_id"] == "image-1"
    assert captured == {"address": "unit1.local", "endpoint": "/unit_api/task_results/task-1"}


def test_run_job(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
        },
    }

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )

    # wrong experiment!
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp99",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 0

    # not active!
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit4/jobs/run/job_name/stirring/experiments/exp3",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 0


def test_run_job_omits_incomplete_model_metadata(client) -> None:
    from pioreactor.web.app import modify_app_db

    modify_app_db(
        "UPDATE workers SET model_name = NULL, model_version = NULL WHERE pioreactor_unit = ?",
        ("unit1",),
    )

    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={},
        )

    assert len(bucket) == 1
    assert "MODEL_NAME" not in bucket[0].json["env"]
    assert "MODEL_VERSION" not in bucket[0].json["env"]


def test_run_job_with_job_source(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}, "env": {"JOB_SOURCE": "experiment_profile"}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "JOB_SOURCE": "experiment_profile",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
        },
    }

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )


@pytest.mark.slow
def test_run_job_response(client) -> None:
    # regression test
    run_post_response = client.post(
        "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
        json={"options": {"target_rpm": 10}},
    )
    assert run_post_response.status_code == 202
    task_data = run_post_response.get_json()

    multicast_task_query_response = client.get(task_data["result_url_path"])
    assert multicast_task_query_response.status_code == 200
    multicast_task_data = multicast_task_query_response.get_json()
    assert multicast_task_data["status"] == "succeeded"

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )


def test_stop_specific_job_returns_task_response_when_mqtt_publish_fails(client, monkeypatch) -> None:
    import pioreactor.web.api as mod

    class DummyTask:
        id = "fallback-task"

    monkeypatch.setattr(
        mod,
        "create_client",
        lambda *_args, **_kwargs: FakeMQTTClient(
            message_info_factory=lambda: FakeMQTTMessageInfo(wait_error=RuntimeError("mqtt down"))
        ),
    )
    monkeypatch.setattr(mod.tasks, "multicast_post", lambda *_args, **_kwargs: DummyTask())

    response = client.post("/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1")

    assert response.status_code == 202
    data = response.get_json()
    assert data["task_id"] == "fallback-task"
    assert data["result_url_path"] == "/unit_api/task_results/fallback-task"


def test_stop_specific_job_returns_accepted_when_mqtt_publish_succeeds(client, monkeypatch) -> None:
    import pioreactor.web.api as mod

    monkeypatch.setattr(mod, "create_client", lambda *_args, **_kwargs: FakeMQTTClient())

    response = client.post("/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1")

    assert response.status_code == 202
    assert response.get_json() == {"status": "accepted"}


def test_export_datasets_returns_async_task_response(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class DummyTask:
        id = "export-task"

    def fake_export_experiment_data_task(
        experiment: str,
        dataset_names: list[str],
        output: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> DummyTask:
        captured["experiment"] = experiment
        captured["dataset_names"] = dataset_names
        captured["output"] = output
        captured["start_time"] = start_time
        captured["end_time"] = end_time
        captured["partition_by_unit"] = partition_by_unit
        captured["partition_by_experiment"] = partition_by_experiment
        return DummyTask()

    monkeypatch.setenv("RUN_PIOREACTOR", tmp_path.as_posix())
    monkeypatch.setattr(
        "pioreactor.web.api.tasks.export_experiment_data_task", fake_export_experiment_data_task
    )

    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": ["od_readings"],
            "experiment": "exp1",
            "partition_by_unit": True,
            "partition_by_experiment": False,
            "start_time": "2025-11-02T01:30:00-05:00",
            "end_time": None,
        },
    )

    assert response.status_code == 202
    data = response.get_json()
    assert data["task_id"] == "export-task"
    assert data["result_url_path"] == "/unit_api/task_results/export-task"
    assert captured["experiment"] == "exp1"
    assert captured["dataset_names"] == ["od_readings"]
    output_path = Path(str(captured["output"]))
    assert output_path.parent == tmp_path / "exports"
    assert output_path.name.startswith("export_")
    assert output_path.name.endswith(".zip")
    assert captured["start_time"] == "2025-11-02T06:30:00.000Z"
    assert captured["end_time"] is None
    assert captured["partition_by_unit"] is True
    assert captured["partition_by_experiment"] is False


def test_export_datasets_rejects_timezone_naive_bounds(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": ["od_readings"],
            "experiment": "exp1",
            "partition_by_unit": True,
            "partition_by_experiment": False,
            "start_time": "2026-01-01T00:00",
            "end_time": None,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_export_datasets_rejects_reversed_bounds(client: FlaskClient) -> None:
    response = client.post(
        "/api/datasets/exportable/export",
        json={
            "datasets": ["od_readings"],
            "experiment": "exp1",
            "partition_by_unit": True,
            "partition_by_experiment": False,
            "start_time": "2026-01-02T00:00:00Z",
            "end_time": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_export_datasets_to_usb_returns_async_task_response(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class DummyTask:
        id = "usb-export-task"

    def fake_export_experiment_data_to_usb_task(
        experiment: str,
        dataset_names: list[str],
        filename: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> DummyTask:
        captured["experiment"] = experiment
        captured["dataset_names"] = dataset_names
        captured["filename"] = filename
        captured["start_time"] = start_time
        captured["end_time"] = end_time
        captured["partition_by_unit"] = partition_by_unit
        captured["partition_by_experiment"] = partition_by_experiment
        return DummyTask()

    monkeypatch.setattr(
        "pioreactor.web.api.tasks.export_experiment_data_to_usb_task",
        fake_export_experiment_data_to_usb_task,
    )

    response = client.post(
        "/api/datasets/exportable/export-to-usb",
        json={
            "datasets": ["od_readings"],
            "experiment": "exp1",
            "partition_by_unit": True,
            "partition_by_experiment": False,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": None,
        },
    )

    assert response.status_code == 202
    data = response.get_json()
    assert data["task_id"] == "usb-export-task"
    assert captured["experiment"] == "exp1"
    assert captured["dataset_names"] == ["od_readings"]
    assert str(captured["filename"]).startswith("export_")
    assert str(captured["filename"]).endswith(".zip")
    assert captured["start_time"] == "2026-01-01T00:00:00.000Z"
    assert captured["end_time"] is None
    assert captured["partition_by_unit"] is True
    assert captured["partition_by_experiment"] is False


def test_install_plugin_from_leader_usb_targets_selected_unit(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_install_plugin_from_leader_usb_across_units(units: list[str], filepath: str, leader: str) -> str:
        captured["units"] = units
        captured["filepath"] = filepath
        captured["leader"] = leader
        return "task"

    monkeypatch.setattr(
        "pioreactor.web.api.tasks.install_plugin_from_leader_usb_across_units",
        fake_install_plugin_from_leader_usb_across_units,
    )
    monkeypatch.setattr("pioreactor.web.api.get_leader_hostname", lambda: "leader")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post(
        "/api/units/unit1/plugins/install-from-leader-usb",
        json={"filepath": "/run/pioreactor/usb/usb-1/pioreactor_demo-1.0.0-py3-none-any.whl"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"task": "task"}
    assert captured == {
        "units": ["unit1"],
        "filepath": "/run/pioreactor/usb/usb-1/pioreactor_demo-1.0.0-py3-none-any.whl",
        "leader": "leader",
    }


def test_install_plugin_from_leader_usb_accepts_broadcast(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_install_plugin_from_leader_usb_across_units(units: list[str], filepath: str, leader: str) -> str:
        captured["units"] = units
        captured["filepath"] = filepath
        captured["leader"] = leader
        return "task"

    monkeypatch.setattr(
        "pioreactor.web.api.tasks.install_plugin_from_leader_usb_across_units",
        fake_install_plugin_from_leader_usb_across_units,
    )
    monkeypatch.setattr("pioreactor.web.api.get_all_units", lambda: ["leader", "unit1"])
    monkeypatch.setattr("pioreactor.web.api.get_leader_hostname", lambda: "leader")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post(
        "/api/units/$broadcast/plugins/install-from-leader-usb",
        json={"filepath": "/run/pioreactor/usb/usb-1/pioreactor_demo-1.0.0-py3-none-any.whl"},
    )

    assert response.status_code == 202
    assert captured == {
        "units": ["leader", "unit1"],
        "filepath": "/run/pioreactor/usb/usb-1/pioreactor_demo-1.0.0-py3-none-any.whl",
        "leader": "leader",
    }


def test_preview_exportable_dataset_uses_default_row_limit(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    exportable_datasets_dir = tmp_path / "exportable_datasets"
    exportable_datasets_dir.mkdir()
    (exportable_datasets_dir / "test_dataset.yaml").write_text(
        """\
dataset_name: test_dataset
default_order_by: null
description: Test dataset
display_name: Test dataset
has_experiment: false
has_unit: false
table: experiments
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOT_PIOREACTOR", tmp_path.as_posix())

    captured: dict[str, object] = {}

    def fake_query_app_db(
        query: str, args: tuple[object, ...] = (), one: bool = False
    ) -> list[dict[str, object]]:
        captured["query"] = query
        captured["args"] = args
        captured["one"] = one
        return [{"experiment": "exp1"}]

    monkeypatch.setattr("pioreactor.web.api.query_app_db", fake_query_app_db)

    response = client.get("/api/datasets/exportable/test_dataset/preview")

    assert response.status_code == 200
    assert response.get_json() == [{"experiment": "exp1"}]
    assert captured["query"] == "SELECT * FROM (experiments) LIMIT ?;"
    assert captured["args"] == (5,)
    assert captured["one"] is False


def test_preview_exportable_dataset_accepts_small_row_limit(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    exportable_datasets_dir = tmp_path / "exportable_datasets"
    exportable_datasets_dir.mkdir()
    (exportable_datasets_dir / "test_dataset.yaml").write_text(
        """\
dataset_name: test_dataset
default_order_by: null
description: Test dataset
display_name: Test dataset
has_experiment: false
has_unit: false
table: experiments
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOT_PIOREACTOR", tmp_path.as_posix())

    response = client.get("/api/datasets/exportable/test_dataset/preview?n_rows=2")

    assert response.status_code == 200
    assert len(response.get_json()) == 2


@pytest.mark.parametrize("n_rows", ["-1", "0", "101", "not-an-int"])
def test_preview_exportable_dataset_rejects_invalid_row_limit(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path, n_rows: str
) -> None:
    exportable_datasets_dir = tmp_path / "exportable_datasets"
    exportable_datasets_dir.mkdir()
    (exportable_datasets_dir / "test_dataset.yaml").write_text(
        """\
dataset_name: test_dataset
default_order_by: null
description: Test dataset
display_name: Test dataset
has_experiment: false
has_unit: false
table: experiments
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOT_PIOREACTOR", tmp_path.as_posix())

    def fake_query_app_db(
        query: str, args: tuple[object, ...] = (), one: bool = False
    ) -> list[dict[str, object]]:
        raise AssertionError("preview should reject invalid n_rows before querying the database")

    monkeypatch.setattr("pioreactor.web.api.query_app_db", fake_query_app_db)

    response = client.get(f"/api/datasets/exportable/test_dataset/preview?n_rows={n_rows}")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid n_rows"


def test_update_app_from_release_archive_requires_json_object(client: FlaskClient) -> None:
    response = client.post(
        "/api/system/update_from_archive",
        data='["not", "an", "object"]',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_update_app_from_release_archive_requires_zip_suffix(
    client: FlaskClient,
) -> None:
    response = client.post(
        "/api/system/update_from_archive",
        json={"release_archive_location": "/tmp/release_26.5.2.zip_1", "units": "$broadcast"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "release_archive_location must point to a .zip file"


def test_update_app_from_release_archive_verifies_renamed_zip_upload(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from pioreactor.release_archive import ReleaseArchiveManifest

    uploaded_archive = tmp_path / "release_26.5.2_1.zip"
    uploaded_archive.write_bytes(b"archive")
    monkeypatch.setattr("pioreactor.web.api.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "pioreactor.web.api.verify_release_archive",
        lambda *_args, **_kwargs: ReleaseArchiveManifest(
            format=1, product="pioreactor", version="26.5.2", files={}
        ),
    )
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    captured: dict[str, str] = {}

    def fake_update_app_from_release_archive_across_cluster(archive_location: str, units: str) -> str:
        captured["archive_location"] = archive_location
        return "task"

    monkeypatch.setattr(
        "pioreactor.web.api.tasks.update_app_from_release_archive_across_cluster",
        fake_update_app_from_release_archive_across_cluster,
    )

    response = client.post(
        "/api/system/update_from_archive",
        json={"release_archive_location": str(uploaded_archive), "units": "$broadcast"},
    )

    assert response.status_code == 202
    assert captured["archive_location"].endswith("_release_26.5.2.zip")


def test_update_app_from_release_archive_requires_units(client: FlaskClient) -> None:
    response = client.post(
        "/api/system/update_from_archive",
        json={"release_archive_location": "/tmp/release.zip"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid request body."


def test_update_app_from_release_archive_verifies_archive_before_queuing(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from pioreactor.release_archive import ReleaseArchiveManifest

    captured: dict[str, object] = {}
    uploaded_archive = tmp_path / "release_26.5.2_1.zip"
    uploaded_archive.write_bytes(b"archive")
    monkeypatch.setattr("pioreactor.web.api.tempfile.gettempdir", lambda: str(tmp_path))

    def fake_verify_release_archive(
        archive_location: str, expected_version: str | None = None
    ) -> ReleaseArchiveManifest:
        captured["verified_archive_location"] = archive_location
        captured["verified_expected_version"] = expected_version
        return ReleaseArchiveManifest(format=1, product="pioreactor", version="26.5.2", files={})

    def fake_update_app_from_release_archive_across_cluster(archive_location: str, units: str) -> str:
        captured["archive_location"] = archive_location
        captured["units"] = units
        return "task"

    monkeypatch.setattr("pioreactor.web.api.verify_release_archive", fake_verify_release_archive)
    monkeypatch.setattr(
        "pioreactor.web.api.tasks.update_app_from_release_archive_across_cluster",
        fake_update_app_from_release_archive_across_cluster,
    )
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post(
        "/api/system/update_from_archive",
        json={"release_archive_location": str(uploaded_archive), "units": "$broadcast"},
    )

    assert response.status_code == 202
    assert captured["verified_archive_location"] == str(uploaded_archive)
    assert captured["verified_expected_version"] is None
    assert captured["units"] == "$broadcast"
    staged_archive_location = Path(str(captured["archive_location"]))
    assert staged_archive_location.parent == tmp_path
    assert staged_archive_location.name.startswith("pioreactor_update_archive_")
    assert staged_archive_location.name.endswith("_release_26.5.2.zip")
    assert staged_archive_location.read_bytes() == b"archive"


def test_update_app_from_release_archive_rejects_unverified_archive(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    from pioreactor.release_archive import ReleaseArchiveVerificationError

    queued = False

    def fake_verify_release_archive(_archive_location: str, expected_version: str | None = None) -> None:
        raise ReleaseArchiveVerificationError("bad signature")

    def fake_update_app_from_release_archive_across_cluster(_archive_location: str, units: str) -> str:
        nonlocal queued
        queued = True
        return "task"

    monkeypatch.setattr("pioreactor.web.api.verify_release_archive", fake_verify_release_archive)
    monkeypatch.setattr(
        "pioreactor.web.api.tasks.update_app_from_release_archive_across_cluster",
        fake_update_app_from_release_archive_across_cluster,
    )

    response = client.post(
        "/api/system/update_from_archive",
        json={"release_archive_location": "/tmp/release_26.5.2.zip", "units": "$broadcast"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Release archive failed verification"
    assert queued is False


@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_unit_api(client) -> None:
    from pioreactor.background_jobs.stirring import start_stirring

    with start_stirring():
        r = client.get(
            "/unit_api/jobs/settings/job_name/stirring",
        )
        assert r.json["settings"]["$state"] == "ready"
        assert r.json["settings"]["target_rpm"] == 500.0

        r = client.get(
            "/unit_api/jobs/settings/job_name/stirring/setting/target_rpm",
        )
        r.json["target_rpm"] == "500.0"


@pytest.mark.slow
@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_api(client) -> None:
    from pioreactor.background_jobs.stirring import start_stirring

    with start_stirring(unit="unit1", experiment="exp1"):
        r = client.get("/api/workers/$broadcast/jobs/settings/job_name/stirring/experiments/exp1")
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit2"]["ok"] is False
        assert settings_per_unit["unit1"]["ok"] is True
        assert settings_per_unit["unit1"]["value"]["settings"]["target_rpm"] == 500.0

        # next api
        r = client.get("/api/workers/unit1/jobs/settings/job_name/stirring/experiments/exp1")
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit1"]["ok"] is True
        assert settings_per_unit["unit1"]["value"]["settings"]["target_rpm"] == 500.0


def test_get_settings_descriptors(client) -> None:
    response = client.get("/api/settings/descriptors")

    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_get_job_descriptors_for_worker_proxies_unit_api(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    def fake_get_from(*_args, **_kwargs) -> MureqResponse:
        return MureqResponse(
            "http://unit1.local:4999/unit_api/jobs/descriptors",
            200,
            {"Content-Type": "application/json"},
            b'[{"job_name":"worker_plugin","display_name":"Worker plugin","display":true,"published_settings":[]}]',
        )

    monkeypatch.setattr(mod, "get_from", fake_get_from)
    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")

    response = client.get("/api/workers/unit1/jobs/descriptors")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "job_name": "worker_plugin",
            "display_name": "Worker plugin",
            "display": True,
            "published_settings": [],
        }
    ]


def test_get_settings_descriptors_for_worker_proxies_unit_api(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    def fake_get_from(*_args, **_kwargs) -> MureqResponse:
        return MureqResponse(
            "http://unit1.local:4999/unit_api/settings/descriptors",
            200,
            {"Content-Type": "application/json"},
            b'[{"key":"worker_settings","display_name":"Worker settings","display":true,"published_settings":[]}]',
        )

    monkeypatch.setattr(mod, "get_from", fake_get_from)
    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")

    response = client.get("/api/workers/unit1/settings/descriptors")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "key": "worker_settings",
            "display_name": "Worker settings",
            "display": True,
            "published_settings": [],
        }
    ]


def test_get_job_descriptors_for_worker_rejects_broadcast(client) -> None:
    response = client.get("/api/workers/$broadcast/jobs/descriptors")

    assert response.status_code == 400
    assert response.mimetype == "application/json"
    data = response.get_json()
    assert data["error"] == "Cannot fetch job descriptors with $broadcast; choose a specific Pioreactor."
    assert data["status"] == 400


def test_get_settings_descriptors_for_worker_rejects_broadcast(client) -> None:
    response = client.get("/api/workers/$broadcast/settings/descriptors")

    assert response.status_code == 400
    assert response.mimetype == "application/json"
    data = response.get_json()
    assert data["error"] == "Cannot fetch settings descriptors with $broadcast; choose a specific Pioreactor."
    assert data["status"] == 400


def test_get_automation_descriptors_for_worker_proxies_unit_api(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    def fake_get_from(*_args, **_kwargs) -> MureqResponse:
        return MureqResponse(
            "http://unit1.local:4999/unit_api/automations/descriptors/dosing",
            200,
            {"Content-Type": "application/json"},
            b'[{"automation_name":"worker_automation","display_name":"Worker automation","description":"Worker-only automation","fields":[]}]',
        )

    monkeypatch.setattr(mod, "get_from", fake_get_from)
    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")

    response = client.get("/api/workers/unit1/automations/descriptors/dosing")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "automation_name": "worker_automation",
            "display_name": "Worker automation",
            "description": "Worker-only automation",
            "fields": [],
        }
    ]


def test_get_automation_descriptors_for_worker_rejects_broadcast(client) -> None:
    response = client.get("/api/workers/$broadcast/automations/descriptors/dosing")

    assert response.status_code == 400
    data = response.get_json()
    assert (
        data["error"] == "Cannot fetch automation descriptors with $broadcast; choose a specific Pioreactor."
    )


def test_update_bioreactor_on_unit_queues_multicast_patch(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_multicast_patch(endpoint: str, units: list[str], json: dict | None = None) -> str:
        captured["endpoint"] = endpoint
        captured["units"] = units
        captured["json"] = json
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_patch", fake_multicast_patch)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.patch(
        "/api/workers/unit1/bioreactor/update/experiments/exp1",
        json={"values": {"current_volume_ml": 12.5, "alt_media_fraction": 0.4}},
    )

    assert response.status_code == 202
    assert captured["endpoint"] == "/unit_api/bioreactor/experiments/exp1"
    assert captured["units"] == ["unit1"]
    assert captured["json"] == {"values": {"current_volume_ml": 12.5, "alt_media_fraction": 0.4}}


def test_update_bioreactor_on_unit_old_route_is_not_available(client) -> None:
    response = client.patch(
        "/api/workers/unit1/experiments/exp1/bioreactor",
        json={"values": {"current_volume_ml": 12.5}},
    )

    assert response.status_code == 404


def test_update_next_version_defaults_to_broadcast(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_update_app_across_cluster(units: str = "$broadcast") -> str:
        captured["units"] = units
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.update_app_across_cluster", fake_update_app_across_cluster)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/system/update_next_version")
    assert response.status_code == 202
    assert captured["units"] == "$broadcast"


def test_update_next_version_accepts_unit_selection(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_update_app_across_cluster(units: str = "$broadcast") -> str:
        captured["units"] = units
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.update_app_across_cluster", fake_update_app_across_cluster)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/system/update_next_version", json={"units": "unit2"})
    assert response.status_code == 202
    assert captured["units"] == "unit2"


def test_system_upload_uses_unique_staged_temp_archive_name(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("pioreactor.web.api.tempfile.gettempdir", lambda: str(tmp_path))

    response = client.post(
        "/api/system/upload",
        data={"file": (BytesIO(b"archive-bytes"), "release_26.4.2.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    save_path = Path(payload["save_path"])

    assert save_path.parent == tmp_path
    assert save_path.name.startswith("pioreactor_update_archive_")
    assert save_path.name.endswith("_release_26.4.2.zip")
    assert save_path.read_bytes() == b"archive-bytes"


def test_system_upload_rejects_oversized_request_before_staging_file(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("pioreactor.web.api.tempfile.gettempdir", lambda: str(tmp_path))
    archive = tmp_path / "oversized-release.zip"
    with archive.open("wb") as archive_file:
        archive_file.truncate(60_000_001)

    with archive.open("rb") as archive_file:
        response = client.post(
            "/api/system/upload",
            data={"file": (archive_file, "release.zip")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 413
    assert response.get_json()["error"] == "Upload too large"
    assert list(tmp_path.glob("pioreactor_update_archive_*")) == []


def test_zipped_calibrations_unwraps_raw_fanout_envelopes(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("od.yaml", "calibration-data")

    class FakeTask:
        def get(self, blocking: bool, timeout: float) -> dict[str, object]:
            return {
                "unit1": {"ok": True, "unit": "unit1", "value": archive.getvalue()},
                "unit2": {
                    "ok": False,
                    "unit": "unit2",
                    "error": {"kind": "connection_error", "message": "Could not reach unit2."},
                    "status_code": None,
                    "retryable": True,
                },
            }

    monkeypatch.setattr("pioreactor.web.api.fanout.broadcast_get_across_workers", lambda *a, **k: FakeTask())

    response = client.get("/api/workers/$broadcast/zipped_calibrations")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.data), "r") as zf:
        assert zf.read("unit1/od.yaml") == b"calibration-data"
        assert all(not name.startswith("unit2/") for name in zf.namelist())


def test_zipped_dot_pioreactor_single_unit_unwraps_raw_fanout_envelope(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.ini", "[section]\n")

    class FakeTask:
        def get(self, blocking: bool, timeout: float) -> dict[str, object]:
            return {"unit1": {"ok": True, "unit": "unit1", "value": archive.getvalue()}}

    monkeypatch.setattr("pioreactor.web.api.multicast_get_to_unit", lambda *a, **k: FakeTask())

    response = client.get("/api/units/unit1/zipped_dot_pioreactor")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.data), "r") as zf:
        assert zf.read("config.ini") == b"[section]\n"


def test_zipped_dot_pioreactor_single_unit_rejects_failed_fanout_envelope(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    class FakeTask:
        def get(self, blocking: bool, timeout: float) -> dict[str, object]:
            return {
                "unit1": {
                    "ok": False,
                    "unit": "unit1",
                    "error": {"kind": "connection_error", "message": "Could not reach unit1."},
                    "status_code": None,
                    "retryable": True,
                }
            }

    monkeypatch.setattr("pioreactor.web.api.multicast_get_to_unit", lambda *a, **k: FakeTask())

    response = client.get("/api/units/unit1/zipped_dot_pioreactor")

    assert response.status_code == 502
    assert response.get_json()["error"] == "No data received from worker"


def test_multicast_get_with_leader_cache_reuses_cached_unit_payloads(monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.tasks as mod

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    calls = 0

    def fake_multicast_get_uncached(
        endpoint: str,
        units: list[str],
        json: dict[str, object] | list[dict[str, object] | None] | None = None,
        timeout: float = 5.0,
        return_raw: bool = False,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        assert endpoint == "/unit_api/calibrations"
        assert units == ["unit1"]
        assert json is None
        assert timeout == 5.0
        assert return_raw is False
        return {
            "unit1": {
                "ok": True,
                "unit": "unit1",
                "value": {"od90": [{"calibration_name": "cached-on-leader"}]},
            }
        }

    monkeypatch.setattr("pioreactor.web.tasks._multicast_get_uncached", fake_multicast_get_uncached)

    first = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])
    second = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    first_payload = first.get(blocking=True, timeout=1)
    second_payload = second.get(blocking=True, timeout=1)

    assert first_payload == {
        "unit1": {
            "ok": True,
            "unit": "unit1",
            "value": {"od90": [{"calibration_name": "cached-on-leader"}]},
        }
    }
    assert second_payload == first_payload
    assert calls == 1

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])


def test_multicast_get_with_leader_cache_does_not_cache_unit_failures(monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.tasks as mod

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    calls = 0

    def fake_multicast_get_uncached(
        endpoint: str,
        units: list[str],
        json: dict[str, object] | list[dict[str, object] | None] | None = None,
        timeout: float = 5.0,
        return_raw: bool = False,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "unit1": {
                    "ok": False,
                    "unit": "unit1",
                    "error": {"kind": "connection_error", "message": "Could not reach unit1."},
                    "status_code": None,
                    "retryable": True,
                }
            }
        return {
            "unit1": {
                "ok": True,
                "unit": "unit1",
                "value": {"od90": [{"calibration_name": "after-retry"}]},
            }
        }

    monkeypatch.setattr("pioreactor.web.tasks._multicast_get_uncached", fake_multicast_get_uncached)

    first = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])
    second = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    assert first.get(blocking=True, timeout=1)["unit1"]["ok"] is False
    assert second.get(blocking=True, timeout=1) == {
        "unit1": {
            "ok": True,
            "unit": "unit1",
            "value": {"od90": [{"calibration_name": "after-retry"}]},
        }
    }
    assert calls == 2

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])


def test_get_all_calibrations_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/calibrations")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "calibrations"
    assert captured["endpoint"] == "/unit_api/calibrations"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_calibration_protocols_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/calibration_protocols")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "calibration_protocols"
    assert captured["endpoint"] == "/unit_api/calibration_protocols"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_all_active_calibrations_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/active_calibrations")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "active_calibrations"
    assert captured["endpoint"] == "/unit_api/active_calibrations"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_create_calibration_invalidates_cached_worker_payloads(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post(
        "/api/workers/unit1/calibrations/media_pump",
        json={"calibration_data": _build_valid_calibration_yaml("uploaded_for_cache"), "set_as_active": True},
    )

    assert response.status_code == 202
    assert captured_calls == [
        ("calibrations", "/unit_api/calibrations", ["unit1"]),
        ("active_calibrations", "/unit_api/active_calibrations", ["unit1"]),
    ]


def test_get_all_estimators_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/estimators")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "estimators"
    assert captured["endpoint"] == "/unit_api/estimators"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_all_active_estimators_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/active_estimators")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "active_estimators"
    assert captured["endpoint"] == "/unit_api/active_estimators"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_set_active_estimator_invalidates_estimator_cache(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_patch", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.patch("/api/workers/unit1/active_estimators/od90/example-estimator")

    assert response.status_code == 202
    assert captured_calls == [
        ("active_estimators", "/unit_api/active_estimators", ["unit1"]),
        ("estimators", "/unit_api/estimators", ["unit1"]),
    ]


def test_get_plugins_on_machine_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/units/$broadcast/plugins/installed")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "plugins_installed"
    assert captured["endpoint"] == "/unit_api/plugins/installed"
    assert set(captured["units"]) == {"localhost", "unit1", "unit2", "unit3", "unit4"}
    assert captured["timeout"] == 5.0


def test_install_plugin_invalidates_plugins_cache(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/units/unit1/plugins/install", json={"args": ["example-plugin"]})

    assert response.status_code == 202
    assert captured_calls == [
        ("plugins_installed", "/unit_api/plugins/installed", ["unit1"]),
        ("calibration_protocols", "/unit_api/calibration_protocols", ["unit1"]),
    ]
