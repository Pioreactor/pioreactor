# -*- coding: utf-8 -*-
import json
from typing import Any

import pytest
from huey.exceptions import ResultTimeout
from huey.exceptions import TaskException
from pioreactor.mureq import Response
from pioreactor.web import tasks


def _response(status_code: int, payload: dict[str, Any]) -> Response:
    return Response("http://unit.local", status_code, {}, json.dumps(payload).encode())


def test_get_from_unit_retries_until_result(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate two pending responses followed by a completed task.
    responses = [
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(202, {"result_url_path": "/unit_api/task_results/abc"}),
        _response(200, {"task_id": "abc", "result": {"ok": True}}),
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


def test_collect_multicast_results_returns_partial_on_timeout() -> None:
    class FakeResult:
        def __init__(self, value: Any = None, error: Exception | None = None) -> None:
            self._value = value
            self._error = error

        def get(self, blocking: bool = False) -> Any:
            if self._error is not None:
                raise self._error
            return self._value

    class FakeResultGroup:
        def __init__(self, results: list[FakeResult]) -> None:
            self._results = results

        def get(self, *args: Any, **kwargs: Any) -> Any:
            raise ResultTimeout("timed out waiting for result")

        def __iter__(self):
            return iter(self._results)

    units = ["unit1", "unit2"]
    results = [
        FakeResult(("unit1", {"ok": True})),
        FakeResult(error=TaskException("boom")),
    ]
    group = FakeResultGroup(results)

    output = tasks._collect_multicast_results(units, group, timeout=0.01)

    assert output == {"unit1": {"ok": True}, "unit2": None}
