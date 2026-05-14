# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import subprocess
import sys
from http.client import HTTPMessage
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any

import pytest
from huey.exceptions import RateLimitExceeded
from pioreactor.mureq import Response
from pioreactor.web import db as web_db
from pioreactor.web import tasks


def _response(status_code: int, payload: dict[str, Any]) -> Response:
    return Response("http://unit.local", status_code, HTTPMessage(), json.dumps(payload).encode())


def _clear_rate_limit(name: str) -> None:
    tasks.huey.delete(f"{tasks.huey.name}.rl.{name}.w")
    tasks.huey.storage.delete_counter(f"{tasks.huey.name}.rl.{name}")


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

    result = tasks.delete_experiment_task.call_local("exp1")

    assert result["result"] is True
    assert result["experiment"] == "exp1"
    assert result["msg"] == "Deleted experiment"
    assert result["database_space"]["reclaimable_bytes"] >= 0

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM experiments WHERE experiment='exp1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0


def test_get_from_unit_retries_until_result(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate two pending responses followed by a completed task.
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(200, {"task_id": "abc", "status": "succeeded", "result": {"ok": True}}),
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

    unit, result = tasks._get_from_unit("unit1", "/unit_api/do", max_attempts=2)

    assert unit == "unit1"
    assert result == {"ok": True}
    assert responses == []


def test_get_from_unit_uses_timeout_for_delayed_task_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_default_window = 60
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"})
        for _ in range(old_default_window + 1)
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
    assert result == {"ok": True}
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
    assert result is None
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
        "task_id": "abc",
        "status": "failed",
        "error": "No such command.",
        "cause": "Huey task failed with an exception.",
    }


def test_check_model_hardware_skips_non_v1_hat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "hardware_version_info", (2, 0))
    monkeypatch.setattr(
        tasks,
        "_get_adc_addresses_for_model",
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
    monkeypatch.setattr(tasks, "hardware_version_info", (1, 2))
    monkeypatch.setattr(tasks, "_get_adc_addresses_for_model", lambda *_args: {0x48})
    monkeypatch.setattr(tasks.hardware, "is_i2c_device_present", lambda address: address == 0x48)

    assert tasks.check_model_hardware.call_local("pioreactor_20ml", "1.1") == {"status": "ok"}


def test_reduce_multicast_results_handles_partial_failures() -> None:
    units = ["unit1", "unit2", "unit3"]
    ordered_results = [
        ("unit1", {"ok": True}),
        RuntimeError("boom"),
        None,
    ]

    output = tasks.reduce_multicast_results.call_local(units, False, ordered_results)
    helper_output = tasks._reduce_multicast_results(units, False, ordered_results)

    assert output == {"unit1": {"ok": True}, "unit2": None, "unit3": None}
    assert helper_output == output


def test_reduce_multicast_results_sorts_when_requested() -> None:
    units = ["unit2", "unit1"]
    ordered_results = [
        ("unit2", {"value": 2}),
        ("unit1", {"value": 1}),
    ]

    output = tasks.reduce_multicast_results.call_local(units, True, ordered_results)

    assert list(output.keys()) == ["unit1", "unit2"]


def test_multicast_get_uncached_allows_headroom_for_aggregate_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class DummyResult:
        def get(self, blocking: bool, timeout: float) -> dict[str, Any]:
            captured["blocking"] = blocking
            captured["timeout"] = timeout
            return {"unit1": None}

    monkeypatch.setattr(tasks, "_enqueue_multicast_chord", lambda *args, **kwargs: DummyResult())

    output = tasks._multicast_get_uncached("/unit_api/calibration_protocols", ["unit1"], timeout=5.0)

    assert output == {"unit1": None}
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
                ReadyChildResult(("unit1", {"ok": True})),
                PendingChildResult(),
            ]

        def get(self, blocking: bool, timeout: float) -> dict[str, Any]:
            raise tasks.ResultTimeout("timed out waiting for result")

    monkeypatch.setattr(tasks, "_enqueue_multicast_chord", lambda *args, **kwargs: DummyResult())

    output = tasks._multicast_get_uncached("/unit_api/calibration_protocols", ["unit1", "unit2"])

    assert output == {"unit1": {"ok": True}, "unit2": None}


def test_install_plugin_task_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_rate_limit("plugins")
    monkeypatch.setattr(
        "pioreactor.plugin_management.install_plugin.install_plugin", lambda *args, **kwargs: None
    )

    assert tasks.install_plugin_task.call_local("demo-plugin") is True

    with pytest.raises(RateLimitExceeded):
        tasks.install_plugin_task.call_local("demo-plugin")

    _clear_rate_limit("plugins")


def test_export_experiment_data_task_cleans_partial_artifacts_and_returns_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "export.zip"
    stale_csv = tmp_path / "old.csv"
    stale_tmp = tmp_path / ".old.zip.tmp"
    stale_csv.write_text("old", encoding="utf-8")
    stale_tmp.write_text("old", encoding="utf-8")

    def fake_export_experiment_data(
        experiments: list[str],
        dataset_names: list[str],
        output: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> None:
        output_path.write_text("zip", encoding="utf-8")

    monkeypatch.setattr(
        "pioreactor.actions.leader.export_experiment_data.export_experiment_data",
        fake_export_experiment_data,
    )

    result = tasks.export_experiment_data_task.call_local(
        ["exp1"],
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
            ["exp1"],
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
        experiments: list[str],
        dataset_names: list[str],
        output: str,
        start_time: str | None = None,
        end_time: str | None = None,
        partition_by_unit: bool = False,
        partition_by_experiment: bool = True,
    ) -> None:
        assert output == (export_dir / "export.zip").as_posix()
        Path(output).write_text("zip", encoding="utf-8")

    monkeypatch.setattr(tasks.usb_utils, "get_usb_export_directory", lambda: export_dir)
    monkeypatch.setattr(
        "pioreactor.actions.leader.export_experiment_data.export_experiment_data",
        fake_export_experiment_data,
    )

    result = tasks.export_experiment_data_to_usb_task.call_local(
        ["exp1"],
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

    monkeypatch.setattr(tasks.usb_utils, "resolve_usb_plugin_wheel", lambda _filepath: wheel)
    monkeypatch.setattr("pioreactor.plugin_management.install_plugin.install_plugin", fake_install_plugin)

    assert tasks.install_plugin_from_usb_task.call_local(wheel.as_posix()) is True
    assert installed == {"name": "pioreactor-demo", "source": wheel.as_posix()}
    _clear_rate_limit("plugins")


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
