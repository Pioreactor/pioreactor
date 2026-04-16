# -*- coding: utf-8 -*-
import json
from http.client import HTTPMessage
from typing import Any

import pytest
from pioreactor.mureq import Response
from pioreactor.web import tasks


def _response(status_code: int, payload: dict[str, Any]) -> Response:
    return Response("http://unit.local", status_code, HTTPMessage(), json.dumps(payload).encode())


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
