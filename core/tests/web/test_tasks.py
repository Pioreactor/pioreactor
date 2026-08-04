# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from datetime import UTC
from http.client import HTTPMessage
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any

import pytest
from huey.exceptions import RateLimitExceeded
from huey.storage import SqliteStorage
from pioreactor.camera import CameraStillMetadata
from pioreactor.mureq import Response
from pioreactor.web import db as web_db
from pioreactor.web import tasks


def _response(status_code: int, payload: dict[str, Any]) -> Response:
    return Response("http://unit.local", status_code, HTTPMessage(), json.dumps(payload).encode())


def _clear_rate_limit(name: str) -> None:
    tasks.huey.delete(f"{tasks.huey.name}.rl.{name}.w")
    tasks.huey.storage.delete_counter(f"{tasks.huey.name}.rl.{name}")


def _clear_lock(name: str) -> None:
    tasks.huey.delete(f"{tasks.huey.name}.lock.{name}")


def test_importing_tasks_does_not_import_web_app() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import pioreactor.web.tasks; print('pioreactor.web.app' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**dict(os.environ), "SKIP_PLUGINS": "1"},
    )

    assert result.stdout.strip() == "False"


def test_periodic_camera_capture_noops_when_camera_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("camera-lock")
    monkeypatch.setattr(tasks, "camera_snapshot_interval_minutes", lambda: 1)
    monkeypatch.setattr(tasks, "get_unit_name", lambda: "unit-a")
    monkeypatch.setattr(tasks.whoami, "get_assigned_experiment_name", lambda unit: "experiment-a")
    monkeypatch.setattr(tasks, "get_camera_status", lambda unit: {"capture_available": False})

    result = tasks.capture_camera_still_periodic_task.call_local()

    assert result == {"captured": False, "reason": "camera_unavailable"}


def test_periodic_camera_capture_noops_when_auto_capture_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("camera-lock")
    monkeypatch.setattr(tasks, "camera_snapshot_interval_minutes", lambda: 1)
    monkeypatch.setattr(tasks, "camera_auto_capture_is_enabled", lambda: False)
    monkeypatch.setattr(
        tasks,
        "get_unit_name",
        lambda: pytest.fail("disabled camera auto-capture must not inspect the unit"),
    )

    result = tasks.capture_camera_still_periodic_task.call_local()

    assert result == {"captured": False, "reason": "disabled"}


def test_periodic_camera_capture_noops_when_worker_is_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("camera-lock")
    monkeypatch.setattr(tasks, "camera_snapshot_interval_minutes", lambda: 1)
    monkeypatch.setattr(tasks, "get_unit_name", lambda: "unit-a")
    monkeypatch.setattr(tasks.whoami, "is_active", lambda unit: False)
    monkeypatch.setattr(tasks.whoami, "get_assigned_experiment_name", lambda unit: "experiment-a")
    monkeypatch.setattr(
        tasks,
        "get_camera_status",
        lambda unit: pytest.fail("inactive workers must not probe the camera"),
    )

    result = tasks.capture_camera_still_periodic_task.call_local()

    assert result == {"captured": False, "reason": "inactive"}


def test_periodic_camera_capture_captures_when_snapshot_is_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("camera-lock")
    captured: dict[str, str | None] = {}
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        image_id="image-a",
    )

    def fake_capture_camera_still(
        unit: str, *, experiment: str | None, capture_reason: str
    ) -> CameraStillMetadata:
        captured["unit"] = unit
        captured["experiment"] = experiment
        captured["capture_reason"] = capture_reason
        return metadata

    monkeypatch.setattr(tasks, "camera_snapshot_interval_minutes", lambda: 1)
    monkeypatch.setattr(tasks, "get_unit_name", lambda: "unit-a")
    monkeypatch.setattr(tasks.whoami, "get_assigned_experiment_name", lambda unit: "experiment-a")
    monkeypatch.setattr(tasks, "get_camera_status", lambda unit: {"capture_available": True})
    monkeypatch.setattr(tasks, "camera_snapshot_is_due", lambda unit, experiment, interval: True)
    monkeypatch.setattr(tasks, "capture_camera_still", fake_capture_camera_still)

    result = tasks.capture_camera_still_periodic_task.call_local()

    assert result["captured"] is True
    assert result["still"]["image_id"] == "image-a"
    assert captured == {
        "unit": "unit-a",
        "experiment": "experiment-a",
        "capture_reason": "scheduled",
    }


def test_huey_lifecycle_starts_and_stops_camera_warmer(monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle: list[str] = []
    monkeypatch.setattr(tasks, "get_plugins", lambda: [])
    monkeypatch.setattr(tasks, "start_camera_warmer", lambda: lifecycle.append("start") or True)
    monkeypatch.setattr(tasks, "stop_camera_warmer", lambda: lifecycle.append("stop"))

    tasks.initialized()
    tasks.clean_up_camera_warmer()

    assert lifecycle == ["start", "stop"]


@pytest.mark.parametrize(
    ("is_manual_focus_session", "expected_capture_reason"),
    [(False, "manual"), (True, "manual_focus")],
)
def test_user_requested_camera_capture_records_capture_reason(
    is_manual_focus_session: bool,
    expected_capture_reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("camera-lock")
    captured_reasons: list[str] = []
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        image_id="image-a",
    )

    def fake_capture_camera_still(
        unit: str, *, experiment: str | None, capture_reason: str
    ) -> CameraStillMetadata:
        captured_reasons.append(capture_reason)
        return metadata

    monkeypatch.setattr(tasks, "capture_camera_still", fake_capture_camera_still)

    tasks.capture_camera_still_task.call_local("unit-a", "experiment-a", is_manual_focus_session)

    assert captured_reasons == [expected_capture_reason]


@pytest.mark.parametrize(
    ("now", "captured_at", "interval_minutes", "expected"),
    [
        (
            datetime(2026, 6, 10, 12, 0, 59, tzinfo=UTC),
            datetime(2026, 6, 10, 12, 0, 1, tzinfo=UTC),
            1,
            False,
        ),
        (
            datetime(2026, 6, 10, 12, 1, 45, tzinfo=UTC),
            datetime(2026, 6, 10, 12, 0, 46, tzinfo=UTC),
            1,
            True,
        ),
        (
            datetime(2026, 6, 10, 12, 1, 45, tzinfo=UTC),
            datetime(2026, 6, 10, 12, 0, 46, tzinfo=UTC),
            2,
            False,
        ),
        (
            datetime(2026, 6, 10, 12, 2, 45, tzinfo=UTC),
            datetime(2026, 6, 10, 12, 0, 46, tzinfo=UTC),
            2,
            True,
        ),
    ],
)
def test_camera_snapshot_is_due_uses_scheduler_minute_intervals(
    now: datetime,
    captured_at: datetime,
    interval_minutes: int,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=captured_at,
        image_id="image-a",
    )
    monkeypatch.setattr(tasks, "current_utc_datetime", lambda: now)
    monkeypatch.setattr(
        tasks,
        "list_camera_still_metadata",
        lambda unit, *, experiment, limit: [metadata],
    )

    assert tasks.camera_snapshot_is_due("unit-a", "experiment-a", interval_minutes) is expected


def test_camera_snapshot_interval_minutes_rejects_negative_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks.pioreactor_config,
        "getint",
        lambda section, option, *, fallback: -1,
    )

    with pytest.raises(ValueError, match="must be 0 or a positive integer"):
        tasks.camera_snapshot_interval_minutes()


def test_camera_focus_calibration_action_uses_existing_capture_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = object()
    captured: dict[str, str | bool | None] = {}

    def fake_capture_task(unit: str, experiment: str | None, is_manual_focus_session: bool) -> object:
        captured["unit"] = unit
        captured["experiment"] = experiment
        captured["is_manual_focus_session"] = is_manual_focus_session
        return task

    monkeypatch.setattr(tasks, "capture_camera_still_task", fake_capture_task)

    handler = tasks.get_calibration_action("camera_focus_capture")
    returned_task, error_label, normalize = handler({"unit": "unit-a", "experiment": "session-a"})

    assert returned_task is task
    assert error_label == "Camera snapshot"
    assert normalize({"image_id": "image-a"}) == {"image_id": "image-a"}
    assert captured == {
        "unit": "unit-a",
        "experiment": "session-a",
        "is_manual_focus_session": True,
    }


def test_delete_camera_stills_task_deletes_each_requested_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[tuple[str, str, str]] = []

    def fake_delete_camera_still(unit: str, experiment: str, image_id: str) -> object | None:
        deleted.append((unit, experiment, image_id))
        return object() if image_id == "image-a" else None

    monkeypatch.setattr(tasks, "delete_camera_still", fake_delete_camera_still)

    result = tasks.delete_camera_stills_task.call_local(
        "unit-a",
        "session-a",
        ["image-a", "image-b"],
    )

    assert result == {"deleted_image_ids": ["image-a"]}
    assert deleted == [
        ("unit-a", "session-a", "image-a"),
        ("unit-a", "session-a", "image-b"),
    ]


def test_camera_focus_cleanup_action_uses_delete_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = object()
    captured: dict[str, object] = {}

    def fake_delete_task(unit: str, experiment: str, image_ids: list[str]) -> object:
        captured.update(unit=unit, experiment=experiment, image_ids=image_ids)
        return task

    monkeypatch.setattr(tasks, "delete_camera_stills_task", fake_delete_task)

    handler = tasks.get_calibration_action("camera_focus_cleanup")
    returned_task, error_label, normalize = handler(
        {
            "unit": "unit-a",
            "experiment": "session-a",
            "image_ids": ["image-a", "image-b"],
        }
    )

    assert returned_task is task
    assert error_label == "Camera focus snapshot cleanup"
    assert normalize({"deleted_image_ids": ["image-a", "image-b"]}) == {
        "deleted_image_ids": ["image-a", "image-b"]
    }
    assert captured == {
        "unit": "unit-a",
        "experiment": "session-a",
        "image_ids": ["image-a", "image-b"],
    }


def test_delete_experiment_task_deletes_and_reports_reclaimable_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE experiments (
                experiment TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE workers (
                pioreactor_unit TEXT NOT NULL UNIQUE
            );
            CREATE TABLE logs (
                experiment TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY (experiment) REFERENCES experiments (experiment) ON DELETE CASCADE
            );
            INSERT INTO experiments (experiment, created_at) VALUES ('exp1', '2026-01-01T00:00:00Z');
            INSERT INTO workers (pioreactor_unit) VALUES ('unit1'), ('unit2');
            INSERT INTO logs (experiment, message) VALUES ('exp1', 'hello');
            """
        )

    original_config_get = web_db.pioreactor_config.get

    def fake_config_get(section: str, option: str, *args: Any, **kwargs: Any) -> str:
        if section == "storage" and option == "database":
            return str(db_path)
        return original_config_get(section, option, *args, **kwargs)

    monkeypatch.setattr(web_db.pioreactor_config, "get", fake_config_get)

    result = tasks.delete_experiment_records_task.call_local([], "exp1", [])

    assert result["result"] is True
    assert result["experiment"] == "exp1"
    assert result["msg"] == "Deleted experiment"
    assert result["database_space"]["reclaimable_bytes"] >= 0
    assert result["camera_cleanup"] == {}
    assert result["camera_cleanup_failures"] == []

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM experiments WHERE experiment='exp1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0


def test_delete_experiment_records_reports_worker_camera_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE experiments (experiment TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO experiments (experiment, created_at) VALUES ('exp1', '2026-01-01T00:00:00Z')"
        )

    original_config_get = web_db.pioreactor_config.get

    def fake_config_get(section: str, option: str, *args: Any, **kwargs: Any) -> str:
        if section == "storage" and option == "database":
            return str(db_path)
        return original_config_get(section, option, *args, **kwargs)

    monkeypatch.setattr(web_db.pioreactor_config, "get", fake_config_get)
    cleanup_results = [
        (
            "unit1",
            tasks.fanout_success("unit1", {"deleted_image_ids": ["image-a"]}),
        ),
        (
            "unit2",
            tasks.fanout_failure(
                "unit2",
                "connection_error",
                "Could not reach unit2.",
                retryable=True,
            ),
        ),
    ]

    result = tasks.delete_experiment_records_task.call_local(
        cleanup_results,
        "exp1",
        ["unit1", "unit2"],
    )

    assert result["result"] is True
    assert result["camera_cleanup"]["unit1"]["ok"] is True
    assert result["camera_cleanup"]["unit2"]["ok"] is False
    assert result["camera_cleanup_failures"] == ["unit2"]
    assert result["msg"] == "Deleted experiment; camera cleanup failed on unit2"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM experiments WHERE experiment='exp1'").fetchone()[0] == 0


def test_delete_experiment_task_fans_out_camera_cleanup_before_database_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    enqueued_chord = object()
    task_result = object()

    class FakeDeleteFromUnitTask:
        @staticmethod
        def s(unit: str, endpoint: str) -> tuple[str, str, str]:
            return ("delete", unit, endpoint)

    class FakeDeleteRecordsTask:
        @staticmethod
        def s(experiment: str, units: list[str]) -> tuple[str, str, list[str]]:
            return ("callback", experiment, units)

    def fake_chord(headers: list[object], callback: object) -> object:
        captured["headers"] = headers
        captured["callback"] = callback
        return enqueued_chord

    def fake_enqueue(chord: object) -> object:
        captured["enqueued"] = chord
        return task_result

    monkeypatch.setattr(tasks, "delete_from_unit", FakeDeleteFromUnitTask)
    monkeypatch.setattr(tasks, "delete_experiment_records_task", FakeDeleteRecordsTask)
    monkeypatch.setattr(tasks, "huey_chord", fake_chord)
    monkeypatch.setattr(tasks.huey, "enqueue", fake_enqueue)

    result = tasks.delete_experiment_task("experiment a", ["unit1", "unit2"])

    assert result is task_result
    assert captured == {
        "headers": [
            ("delete", "unit1", "/unit_api/camera/experiments/experiment a/stills"),
            ("delete", "unit2", "/unit_api/camera/experiments/experiment a/stills"),
        ],
        "callback": ("callback", "experiment a", ["unit1", "unit2"]),
        "enqueued": enqueued_chord,
    }


def test_get_from_unit_retries_until_result(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate two pending responses followed by a completed task.
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(200, {"task_id": "abc", "status": "succeeded", "result": {"ok": True}}),
    ]
    events: list[str] = []

    # Each request pops the next response in sequence.
    def fake_get_from(
        address: str, endpoint: str, json: dict | None = None, timeout: float = 5.0
    ) -> Response:
        events.append("get")
        return responses.pop(0)

    monkeypatch.setattr(tasks, "get_from", fake_get_from)
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "http://unit.local")
    # Avoid test delays from retry sleeps.
    monkeypatch.setattr(tasks, "sleep", lambda _: events.append("sleep"))

    unit, result = tasks._get_from_unit("unit1", "/unit_api/do", max_attempts=2)

    assert unit == "unit1"
    assert result == {"ok": True, "unit": "unit1", "value": {"ok": True}}
    assert responses == []
    assert events == ["get", "get", "sleep", "get"]


def test_get_from_unit_uses_timeout_for_delayed_task_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shorter_timeout_attempts = tasks._delayed_result_max_attempts(5.0)
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"})
        for _ in range(shorter_timeout_attempts + 1)
    ]
    responses.append(_response(200, {"task_id": "abc", "status": "succeeded", "result": {"ok": True}}))

    def fake_get_from(
        address: str, endpoint: str, json: dict | None = None, timeout: float = 5.0
    ) -> Response:
        return responses.pop(0)

    monkeypatch.setattr(tasks, "get_from", fake_get_from)
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "http://unit.local")
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    unit, result = tasks._get_from_unit("unit1", "/unit_api/do", timeout=7.0)

    assert unit == "unit1"
    assert result == {"ok": True, "unit": "unit1", "value": {"ok": True}}
    assert responses == []


def test_get_from_unit_stops_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate a pending response that never resolves within the attempt limit.
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
    ]

    # Each request pops the next response in sequence.
    def fake_get_from(
        address: str, endpoint: str, json: dict | None = None, timeout: float = 5.0
    ) -> Response:
        return responses.pop(0)

    monkeypatch.setattr(tasks, "get_from", fake_get_from)
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "http://unit.local")
    # Avoid test delays from retry sleeps.
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    unit, result = tasks._get_from_unit("unit1", "/unit_api/do", max_attempts=1)

    assert unit == "unit1"
    assert result == {
        "ok": False,
        "unit": "unit1",
        "error": {"kind": "task_timeout", "message": "Timed out waiting for unit task result."},
        "status_code": 202,
        "retryable": True,
    }
    assert responses == []


def test_get_from_unit_returns_failed_task_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(
            200,
            {
                "task_id": "abc",
                "status": "failed",
                "error": "No such command.",
                "cause": "Huey task failed with an exception.",
            },
        ),
    ]

    def fake_get_from(
        address: str, endpoint: str, json: dict | None = None, timeout: float = 5.0
    ) -> Response:
        return responses.pop(0)

    monkeypatch.setattr(tasks, "get_from", fake_get_from)
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "http://unit.local")
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    unit, result = tasks._get_from_unit("unit1", "/unit_api/do", max_attempts=2)

    assert unit == "unit1"
    assert result == {
        "ok": False,
        "unit": "unit1",
        "error": {
            "kind": "task_failed",
            "message": "No such command.",
            "cause": "Huey task failed with an exception.",
        },
        "status_code": 200,
        "retryable": False,
    }


def test_fanout_success_strips_generic_success_status() -> None:
    assert tasks.fanout_success(
        "unit1",
        {"status": "success", "clock_time": "2026-05-30T02:44:50.585Z"},
    ) == {
        "ok": True,
        "unit": "unit1",
        "value": {"clock_time": "2026-05-30T02:44:50.585Z"},
    }
    assert tasks.fanout_success("unit1", {"status": "success"}) == {
        "ok": True,
        "unit": "unit1",
        "value": {},
    }


def test_check_model_hardware_skips_non_v1_hat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks.hardware, "hardware_version_info", (2, 0))
    monkeypatch.setattr(
        tasks.hardware,
        "get_adc_addresses_for_model",
        lambda *_args: (_ for _ in ()).throw(AssertionError("should not inspect ADCs")),
    )

    assert tasks.check_model_hardware.call_local("pioreactor_20ml", "1.5") == {
        "status": "skipped",
        "reason": "hardware check only applies to HAT v1.x",
    }


def test_repair_system_repairs_permissions_then_checks_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_rate_limit("repair-system")
    calls: list[list[str]] = []

    class DummyResult:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command: list[str], **_kwargs: object) -> DummyResult:
        calls.append(command)
        if command == [tasks.PIO_EXECUTABLE, "status", "--json"]:
            return DummyResult('{"status":"WARN","checks":[]}')
        return DummyResult("ok")

    monkeypatch.setattr(tasks, "run", fake_run)

    result = tasks.repair_system.call_local()

    assert calls == [
        [tasks.PIO_EXECUTABLE, "repair"],
        [tasks.PIO_EXECUTABLE, "status", "--json"],
    ]
    assert result["success"] is True
    assert result["repair"]["stdout"] == "ok"
    assert result["status"]["stdout"] == '{"status":"WARN","checks":[]}'
    assert result["status"]["payload"] == {"status": "WARN", "checks": []}


def test_repair_system_logs_failed_repair_command(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_rate_limit("repair-system")
    warnings: list[tuple[str, tuple[object, ...]]] = []

    class DummyLogger:
        def debug(self, *_args: object, **_kwargs: object) -> None:
            pass

        def warning(self, message: str, *args: object, **_kwargs: object) -> None:
            warnings.append((message, args))

    class DummyResult:
        def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command: list[str], **_kwargs: object) -> DummyResult:
        if command == [tasks.PIO_EXECUTABLE, "repair"]:
            return DummyResult(1, "fixed one thing", "permission denied")
        return DummyResult(0, '{"status":"OK","checks":[]}', "")

    monkeypatch.setattr(tasks, "logger", DummyLogger())
    monkeypatch.setattr(tasks, "run", fake_run)

    result = tasks.repair_system.call_local()

    assert result["success"] is False
    assert warnings == [
        (
            "System repair command failed with return code %s. stdout: %s stderr: %s",
            (1, "fixed one thing", "permission denied"),
        )
    ]


def test_check_model_hardware_runs_for_v1_hat_regardless_of_model_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks.hardware, "hardware_version_info", (1, 2))
    monkeypatch.setattr(tasks.hardware, "get_adc_addresses_for_model", lambda *_args: {0x48})
    monkeypatch.setattr(tasks.hardware, "is_i2c_device_present", lambda address: address == 0x48)

    assert tasks.check_model_hardware.call_local("pioreactor_20ml", "1.1") == {"status": "ok"}


def test_reduce_multicast_results_handles_partial_failures() -> None:
    units = ["unit1", "unit2", "unit3"]
    ordered_results = [
        ("unit1", tasks.fanout_success("unit1", {"ok": True})),
        RuntimeError("boom"),
        None,
    ]

    output = tasks.reduce_multicast_results.call_local(units, False, ordered_results, child_task_ids=[])
    helper_output = tasks._reduce_multicast_results(units, False, ordered_results)

    assert output == {
        "unit1": {"ok": True, "unit": "unit1", "value": {"ok": True}},
        "unit2": {
            "ok": False,
            "unit": "unit2",
            "error": {"kind": "task_exception", "message": "boom"},
            "status_code": None,
            "retryable": True,
        },
        "unit3": {
            "ok": False,
            "unit": "unit3",
            "error": {"kind": "missing_result", "message": "No result returned for unit."},
            "status_code": None,
            "retryable": True,
        },
    }
    assert helper_output == output


def test_reduce_multicast_results_sorts_when_requested() -> None:
    units = ["unit2", "unit1"]
    ordered_results = [
        ("unit2", tasks.fanout_success("unit2", {"value": 2})),
        ("unit1", tasks.fanout_success("unit1", {"value": 1})),
    ]

    output = tasks.reduce_multicast_results.call_local(units, True, ordered_results, child_task_ids=[])

    assert list(output.keys()) == ["unit1", "unit2"]


def test_multicast_chord_deletes_child_results_and_preserves_callback_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks.huey, "_immediate", False)
    monkeypatch.setattr(
        tasks.huey,
        "storage",
        SqliteStorage(tasks.huey.name, filename=tmp_path / "huey.db"),
    )
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: f"http://{unit}.local")
    monkeypatch.setattr(
        tasks,
        "get_from",
        lambda address, endpoint, json=None, timeout=5.0: _response(
            200, {"address": address, "endpoint": endpoint}
        ),
    )

    chord_result = tasks.multicast_get("/unit_api/test", ["unit1", "unit2"])
    child_task_ids = [child_result.id for child_result in chord_result.results]

    for _ in child_task_ids:
        child_task = tasks.huey.dequeue()
        assert child_task is not None
        tasks.huey.execute(child_task)

    assert all(tasks.huey.storage.has_data_for_key(task_id) for task_id in child_task_ids)

    callback_task = tasks.huey.dequeue()
    assert callback_task is not None
    tasks.huey.execute(callback_task)

    assert tasks.huey.dequeue() is None
    assert all(not tasks.huey.storage.has_data_for_key(task_id) for task_id in child_task_ids)
    assert tasks.huey.storage.has_data_for_key(chord_result.callback.id)

    expected = {
        "unit1": {
            "ok": True,
            "unit": "unit1",
            "value": {"address": "http://unit1.local", "endpoint": "/unit_api/test"},
        },
        "unit2": {
            "ok": True,
            "unit": "unit2",
            "value": {"address": "http://unit2.local", "endpoint": "/unit_api/test"},
        },
    }
    assert chord_result.get(preserve=True) == expected
    chord_result.reset()
    assert chord_result.get(preserve=True) == expected


def test_multicast_get_uncached_allows_headroom_for_aggregate_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class DummyResult:
        def get(self, blocking: bool, timeout: float) -> dict[str, Any]:
            captured["blocking"] = blocking
            captured["timeout"] = timeout
            return {
                "unit1": {
                    "ok": False,
                    "unit": "unit1",
                    "error": {"kind": "missing_result", "message": "No result returned for unit."},
                    "status_code": None,
                    "retryable": True,
                }
            }

    monkeypatch.setattr(tasks, "_enqueue_multicast_chord", lambda *args, **kwargs: DummyResult())

    output = tasks._multicast_get_uncached("/unit_api/calibration_protocols", ["unit1"], timeout=5.0)

    assert output == {
        "unit1": {
            "ok": False,
            "unit": "unit1",
            "error": {"kind": "missing_result", "message": "No result returned for unit."},
            "status_code": None,
            "retryable": True,
        }
    }
    assert captured == {"blocking": True, "timeout": 6.0}


def test_multicast_get_uncached_falls_back_to_child_results_when_callback_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadyChildResult:
        def __init__(self, value: Any) -> None:
            self.value = value

        def get(self, blocking: bool = False, preserve: bool = False) -> Any:
            return self.value

    class PendingChildResult:
        def get(self, blocking: bool = False, preserve: bool = False) -> Any:
            return None

    class DummyResult:
        def __init__(self) -> None:
            self.results = [
                ReadyChildResult(("unit1", tasks.fanout_success("unit1", {"ok": True}))),
                PendingChildResult(),
            ]

        def get(self, blocking: bool, timeout: float) -> dict[str, Any]:
            raise tasks.ResultTimeout("timed out waiting for result.")

    monkeypatch.setattr(tasks, "_enqueue_multicast_chord", lambda *args, **kwargs: DummyResult())

    output = tasks._multicast_get_uncached("/unit_api/calibration_protocols", ["unit1", "unit2"])

    assert output == {
        "unit1": {"ok": True, "unit": "unit1", "value": {"ok": True}},
        "unit2": {
            "ok": False,
            "unit": "unit2",
            "error": {"kind": "missing_result", "message": "No result returned for unit."},
            "status_code": None,
            "retryable": True,
        },
    }


def test_export_experiment_data_task_cleans_partial_artifacts_and_returns_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "export.zip"
    stale_csv = tmp_path / "old.csv"
    stale_tmp = tmp_path / ".old.zip.tmp"
    stale_csv.write_text("old", encoding="utf-8")
    stale_tmp.write_text("old", encoding="utf-8")

    def fake_export_experiment_data(
        experiment: str,
        dataset_names: list[str],
        output: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> None:
        assert experiment == "exp1"
        output_path.write_text("zip", encoding="utf-8")

    monkeypatch.setattr(
        "pioreactor.actions.leader.export_experiment_data.export_experiment_data",
        fake_export_experiment_data,
    )

    result = tasks.export_experiment_data_task.call_local(
        "exp1",
        ["od_readings"],
        output_path.as_posix(),
    )

    assert result == {"result": True, "filename": "export.zip", "msg": "Finished"}
    assert not stale_csv.exists()
    assert not stale_tmp.exists()
    assert output_path.exists()


def test_export_experiment_data_task_logs_export_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "export.zip"
    logged_errors: list[tuple[str, bool]] = []

    class FakeLogger:
        def debug(self, *_args: object, **_kwargs: object) -> None:
            pass

        def error(self, message: str, *args: object, **kwargs: object) -> None:
            logged_errors.append((message, bool(kwargs.get("exc_info"))))

    def fake_export_experiment_data(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(tasks, "logger", FakeLogger())
    monkeypatch.setattr(
        "pioreactor.actions.leader.export_experiment_data.export_experiment_data",
        fake_export_experiment_data,
    )

    with pytest.raises(RuntimeError, match="database is locked"):
        tasks.export_experiment_data_task.call_local(
            "exp1",
            ["od_readings"],
            output_path.as_posix(),
        )

    assert logged_errors == [("Exporting experiment data failed: database is locked", True)]


def test_mount_usb_task_mounts_selected_partition(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    partition = tasks.usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PIOREACTOR",
        uuid="7A2B-91FE",
        fstype="exfat",
        size_bytes=1000,
        mountpoints=(),
        removable=True,
    )
    mountpoint = tmp_path / "usb-7A2B-91FE"

    monkeypatch.setattr(tasks.usb_utils, "choose_usb_partition", lambda device=None: partition)
    monkeypatch.setattr(tasks.usb_utils, "mount_usb_partition", lambda _partition: mountpoint)
    monkeypatch.setattr(tasks.whoami, "is_testing_env", lambda: False)

    result = tasks.mount_usb_task.call_local("/dev/sda1")

    assert result == {
        "result": True,
        "device": "/dev/sda1",
        "display_name": "PIOREACTOR",
        "mountpoint": mountpoint.as_posix(),
        "msg": "Mounted",
    }


def test_export_experiment_data_to_usb_task_writes_final_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export_dir = tmp_path / "pioreactor" / "exports"

    def fake_export_experiment_data(
        experiment: str,
        dataset_names: list[str],
        output: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> None:
        assert experiment == "exp1"
        assert output == (export_dir / "export.zip").as_posix()
        Path(output).write_text("zip", encoding="utf-8")

    monkeypatch.setattr(tasks.usb_utils, "get_usb_export_directory", lambda: export_dir)
    monkeypatch.setattr(
        "pioreactor.actions.leader.export_experiment_data.export_experiment_data",
        fake_export_experiment_data,
    )

    result = tasks.export_experiment_data_to_usb_task.call_local(
        "exp1",
        ["od_readings"],
        "export.zip",
    )

    assert result == {
        "result": True,
        "filename": "export.zip",
        "path": (export_dir / "export.zip").as_posix(),
        "msg": "Finished",
    }
    assert (export_dir / "export.zip").read_text(encoding="utf-8") == "zip"
    assert not (export_dir / ".export.zip.tmp.zip").exists()


def test_install_plugin_from_usb_task_installs_resolved_wheel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_rate_limit("plugins")
    installed: dict[str, str | None] = {}
    wheel = tmp_path / "pioreactor_demo-1.2.3-py3-none-any.whl"
    wheel.write_text("wheel", encoding="utf-8")

    def fake_install_plugin(name: str, source: str | None = None) -> None:
        installed["name"] = name
        installed["source"] = source

    monkeypatch.setattr(tasks.usb_utils, "resolve_usb_plugin_artifact", lambda _filepath: wheel)
    monkeypatch.setattr("pioreactor.plugin_management.install_plugin.install_plugin", fake_install_plugin)

    assert tasks.install_plugin_from_usb_task.call_local(wheel.as_posix()) is True
    assert installed == {"name": "pioreactor-demo", "source": wheel.as_posix()}
    _clear_rate_limit("plugins")


def test_install_plugin_from_usb_task_copies_resolved_python_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_rate_limit("plugins")
    source = tmp_path / "dropin_plugin.py"
    source.write_text("__plugin_name__ = 'Drop In'\n", encoding="utf-8")
    dot_pioreactor = tmp_path / "dot_pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", dot_pioreactor.as_posix())
    monkeypatch.setattr(tasks.usb_utils, "resolve_usb_plugin_artifact", lambda _filepath: source)

    assert tasks.install_plugin_from_usb_task.call_local(source.as_posix()) is True
    assert (dot_pioreactor / "plugins" / "dropin_plugin.py").read_text(
        encoding="utf-8"
    ) == "__plugin_name__ = 'Drop In'\n"
    _clear_rate_limit("plugins")


def test_install_plugin_from_leader_usb_on_worker_copies_python_file_to_tmp_then_posts_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "dropin_plugin.py"
    source.write_text("plugin", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"task": "installed"}

    def fake_cp_file_across_cluster(unit: str, localpath: str, remotepath: str, timeout: int) -> None:
        captured["copy"] = (unit, localpath, remotepath, timeout)

    def fake_post_into(address: str, endpoint: str, json: dict[str, str], timeout: int) -> FakeResponse:
        captured["post"] = (address, endpoint, json, timeout)
        return FakeResponse()

    monkeypatch.setattr(tasks.usb_utils, "resolve_usb_plugin_artifact", lambda _filepath: source)
    monkeypatch.setattr(tasks, "cp_file_across_cluster", fake_cp_file_across_cluster)
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(tasks, "post_into", fake_post_into)

    result = tasks._install_plugin_from_leader_usb_on_worker("worker1", source.as_posix())

    assert captured["copy"] == ("worker1", source.as_posix(), "/tmp/dropin_plugin.py", 60)
    assert captured["post"] == (
        "worker1.local",
        "/unit_api/plugins/install-python-file-from-leader-copy",
        {"filename": "dropin_plugin.py"},
        60,
    )
    assert result == {
        "success": True,
        "unit": "worker1",
        "plugin": "dropin_plugin",
        "source": "/tmp/dropin_plugin.py",
        "install_response": {"task": "installed"},
    }


def test_install_plugin_from_leader_usb_across_units_runs_units_sequentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_lock("plugins-lock")
    _clear_lock("usb-lock")
    calls: list[tuple[str, str]] = []

    def fake_install_plugin_from_usb(filepath: str) -> bool:
        calls.append(("leader", filepath))
        return True

    def fake_install_plugin_from_leader_usb_on_worker(unit: str, filepath: str) -> dict[str, str | bool]:
        calls.append((unit, filepath))
        return {
            "success": True,
            "unit": unit,
            "plugin": "pioreactor-demo",
            "source": "/tmp/pioreactor_demo-1.2.3-py3-none-any.whl",
        }

    monkeypatch.setattr(tasks, "_install_plugin_from_usb", fake_install_plugin_from_usb)
    monkeypatch.setattr(
        tasks,
        "_install_plugin_from_leader_usb_on_worker",
        fake_install_plugin_from_leader_usb_on_worker,
    )

    result = tasks.install_plugin_from_leader_usb_across_units_task.call_local(
        ["leader", "worker1", "worker2"],
        "/run/pioreactor/usb/usb-1/pioreactor_demo-1.2.3-py3-none-any.whl",
        "leader",
    )

    assert calls == [
        ("leader", "/run/pioreactor/usb/usb-1/pioreactor_demo-1.2.3-py3-none-any.whl"),
        ("worker1", "/run/pioreactor/usb/usb-1/pioreactor_demo-1.2.3-py3-none-any.whl"),
        ("worker2", "/run/pioreactor/usb/usb-1/pioreactor_demo-1.2.3-py3-none-any.whl"),
    ]
    assert result == {
        "leader": {"ok": True, "unit": "leader", "value": True},
        "worker1": {
            "ok": True,
            "unit": "worker1",
            "value": {
                "success": True,
                "unit": "worker1",
                "plugin": "pioreactor-demo",
                "source": "/tmp/pioreactor_demo-1.2.3-py3-none-any.whl",
            },
        },
        "worker2": {
            "ok": True,
            "unit": "worker2",
            "value": {
                "success": True,
                "unit": "worker2",
                "plugin": "pioreactor-demo",
                "source": "/tmp/pioreactor_demo-1.2.3-py3-none-any.whl",
            },
        },
    }
    _clear_lock("plugins-lock")
    _clear_lock("usb-lock")


def test_export_disk_space_preflight_rejects_low_space(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Usage:
        free = 1

    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _path: Usage())

    with pytest.raises(OSError, match="Not enough free space to export datasets"):
        tasks.require_export_disk_space(tmp_path)


def test_export_disk_space_preflight_allows_minimum_working_space(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Usage:
        free = tasks.MINIMUM_EXPORT_FREE_BYTES

    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _path: Usage())

    tasks.require_export_disk_space(tmp_path)


def test_power_actions_share_rate_limit_bucket() -> None:
    _clear_rate_limit("power-actions")

    assert tasks.reboot.call_local() is True

    with pytest.raises(RateLimitExceeded):
        tasks.shutdown.call_local()

    _clear_rate_limit("power-actions")


def test_write_config_and_sync_is_rate_limited(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _clear_rate_limit("config-sync")

    class FakeCompletedProcess:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(tasks, "run", lambda *args, **kwargs: FakeCompletedProcess())

    config_path = tmp_path / "config.ini"

    assert tasks.write_config_and_sync.call_local(str(config_path), "[ui]\n", "unit1") == (True, "")

    with pytest.raises(RateLimitExceeded):
        tasks.write_config_and_sync.call_local(str(config_path), "[ui]\n", "unit1")

    _clear_rate_limit("config-sync")


def test_pio_run_returns_structured_success_when_process_stays_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProc:
        returncode: int | None = None

        def wait(self, timeout: float) -> None:
            raise TimeoutExpired(cmd="pio run stirring", timeout=timeout)

    monkeypatch.setattr(tasks, "Popen", lambda *args, **kwargs: FakeProc())

    result = tasks.pio_run.call_local("stirring", env={"EXPERIMENT": "exp1"})

    assert result == {"ok": True}


def test_pio_run_returns_success_when_process_exits_zero_during_grace_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProc:
        returncode = 0

        def wait(self, timeout: float) -> None:
            return None

    monkeypatch.setattr(tasks, "Popen", lambda *args, **kwargs: FakeProc())

    result = tasks.pio_run.call_local("led_intensity", "--A", "50", env={"EXPERIMENT": "exp1"})

    assert result == {"ok": True}


def test_pio_run_fast_fail_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProc:
        returncode = 2

        def wait(self, timeout: float) -> None:
            return None

    monkeypatch.setattr(tasks, "Popen", lambda *args, **kwargs: FakeProc())

    with pytest.raises(RuntimeError, match="Command exited during startup grace window. Exit code 2."):
        tasks.pio_run.call_local("circulate_alt_media", "--duration", "bad", env={"EXPERIMENT": "exp1"})


def test_update_app_across_cluster_excludes_leader_from_worker_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    monkeypatch.setattr(tasks, "get_workers_in_inventory", lambda: ("leader", "worker1", "worker2"))
    monkeypatch.setattr(tasks, "get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(tasks, "check_call", lambda cmd: check_calls.append(cmd))

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(tasks, "run", lambda cmd: run_calls.append(cmd) or FakeCompletedProcess())
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    assert tasks.update_app_across_cluster.call_local() is True
    assert check_calls == [
        [tasks.PIO_EXECUTABLE, "update", "app", "--defer-web-restart"],
        ["sudo", "systemctl", "restart", "pioreactor-web.target"],
    ]
    assert run_calls == [
        [tasks.PIOS_EXECUTABLE, "update", "app", "-y", "--units", "worker1", "--units", "worker2"]
    ]


def test_update_app_from_release_archive_across_cluster_skips_worker_phase_without_non_leader_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    monkeypatch.setattr(tasks, "get_workers_in_inventory", lambda: ("leader",))
    monkeypatch.setattr(tasks, "get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(tasks, "check_call", lambda cmd: check_calls.append(cmd))

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(tasks, "run", lambda cmd: run_calls.append(cmd) or FakeCompletedProcess())
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    assert tasks.update_app_from_release_archive_across_cluster.call_local(
        "/tmp/release_26.4.2.zip", "$broadcast"
    )
    assert check_calls == [
        [
            tasks.PIO_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/tmp/release_26.4.2.zip",
            "--defer-web-restart",
        ],
        ["sudo", "systemctl", "restart", "pioreactor-web.target"],
    ]
    assert run_calls == []


def test_update_app_from_release_archive_across_cluster_updates_only_non_leader_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    monkeypatch.setattr(tasks, "get_workers_in_inventory", lambda: ("leader", "worker1", "worker2"))
    monkeypatch.setattr(tasks, "get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(tasks, "check_call", lambda cmd: check_calls.append(cmd))

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(tasks, "run", lambda cmd: run_calls.append(cmd) or FakeCompletedProcess())
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    assert tasks.update_app_from_release_archive_across_cluster.call_local(
        "/tmp/release_26.4.2.zip", "$broadcast"
    )
    assert check_calls == [
        [
            tasks.PIO_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/tmp/release_26.4.2.zip",
            "--defer-web-restart",
        ],
        ["sudo", "systemctl", "restart", "pioreactor-web.target"],
    ]
    assert run_calls == [
        [
            tasks.PIOS_EXECUTABLE,
            "cp",
            "/tmp/release_26.4.2.zip",
            "/tmp/release_26.4.2.zip",
            "-y",
            "--units",
            "worker1",
            "--units",
            "worker2",
        ],
        [
            tasks.PIOS_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/tmp/release_26.4.2.zip",
            "-y",
            "--units",
            "worker1",
            "--units",
            "worker2",
        ],
    ]


def test_update_app_from_usb_release_archive_stages_archive_on_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    monkeypatch.setattr(tasks, "get_workers_in_inventory", lambda: ("leader", "worker1"))
    monkeypatch.setattr(tasks, "get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(tasks, "check_call", lambda cmd: check_calls.append(cmd))

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(tasks, "run", lambda cmd: run_calls.append(cmd) or FakeCompletedProcess())
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    assert tasks.update_app_from_release_archive_across_cluster.call_local(
        "/run/pioreactor/usb/usb-1/release_26.4.2.zip", "$broadcast"
    )
    assert check_calls == [
        [
            tasks.PIO_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/run/pioreactor/usb/usb-1/release_26.4.2.zip",
            "--defer-web-restart",
        ],
        ["sudo", "systemctl", "restart", "pioreactor-web.target"],
    ]
    assert run_calls == [
        [
            tasks.PIOS_EXECUTABLE,
            "cp",
            "/run/pioreactor/usb/usb-1/release_26.4.2.zip",
            "/tmp/release_26.4.2.zip",
            "-y",
            "--units",
            "worker1",
        ],
        [
            tasks.PIOS_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/tmp/release_26.4.2.zip",
            "-y",
            "--units",
            "worker1",
        ],
    ]


def test_update_app_from_release_archive_updates_leader_when_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    monkeypatch.setattr(tasks, "get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(tasks, "check_call", lambda cmd: check_calls.append(cmd))

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(tasks, "run", lambda cmd: run_calls.append(cmd) or FakeCompletedProcess())
    monkeypatch.setattr(tasks, "sleep", lambda _: None)

    assert tasks.update_app_from_release_archive_across_cluster.call_local(
        "/run/pioreactor/usb/usb-1/release_26.4.2.zip", "leader"
    )
    assert check_calls == [
        [
            tasks.PIO_EXECUTABLE,
            "update",
            "app",
            "--source",
            "/run/pioreactor/usb/usb-1/release_26.4.2.zip",
            "--defer-web-restart",
        ],
        ["sudo", "systemctl", "restart", "pioreactor-web.target"],
    ]
    assert run_calls == []
