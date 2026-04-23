# -*- coding: utf-8 -*-
import json
from http.client import HTTPMessage
from subprocess import TimeoutExpired
from typing import Any

import pytest
from huey.exceptions import RateLimitExceeded
from pioreactor.mureq import Response
from pioreactor.web import tasks


def _response(status_code: int, payload: dict[str, Any]) -> Response:
    return Response("http://unit.local", status_code, HTTPMessage(), json.dumps(payload).encode())


def _clear_rate_limit(name: str) -> None:
    tasks.huey.delete(f"{tasks.huey.name}.rl.{name}.w")
    tasks.huey.storage.delete_counter(f"{tasks.huey.name}.rl.{name}")


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


def test_reduce_multicast_results_handles_partial_failures() -> None:
    units = ["unit1", "unit2", "unit3"]
    ordered_results = [
        ("unit1", {"ok": True}),
        RuntimeError("boom"),
        None,
    ]

    output = tasks.reduce_multicast_results.call_local(units, False, ordered_results)

    assert output == {"unit1": {"ok": True}, "unit2": None, "unit3": None}


def test_reduce_multicast_results_sorts_when_requested() -> None:
    units = ["unit2", "unit1"]
    ordered_results = [
        ("unit2", {"value": 2}),
        ("unit1", {"value": 1}),
    ]

    output = tasks.reduce_multicast_results.call_local(units, True, ordered_results)

    assert list(output.keys()) == ["unit1", "unit2"]


def test_install_plugin_task_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_rate_limit("plugins")
    monkeypatch.setattr(
        "pioreactor.plugin_management.install_plugin.install_plugin", lambda *args, **kwargs: None
    )

    assert tasks.install_plugin_task.call_local("demo-plugin") is True

    with pytest.raises(RateLimitExceeded):
        tasks.install_plugin_task.call_local("demo-plugin")

    _clear_rate_limit("plugins")


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
