# -*- coding: utf-8 -*-
from typing import Any
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest
from flask.testing import FlaskClient
from pioreactor.mureq import Response
from pioreactor.web import tasks
from pioreactor.web.app import HOSTNAME

from .conftest import capture_requests


@pytest.mark.parametrize(
    "task_name, method, path",
    [
        ("post_into_unit", "POST", "/unit_api/jobs/stop/all"),
        ("patch_into_unit", "PATCH", "/unit_api/jobs/stop/all"),
        ("delete_from_unit", "DELETE", "/unit_api/calibrations/stirring/example"),
    ],
)
@pytest.mark.parametrize("target", [HOSTNAME, "other-worker"])
def test_queued_mutation_checks_identity_at_destination(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    task_name: str,
    method: str,
    path: str,
    target: str,
) -> None:
    # Both names resolve to the same address, simulating a reused worker IP.
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "192.0.2.42")
    endpoint, _ = client.application.url_map.bind("localhost").match(path, method=method)
    handler = Mock(return_value={"executed": True})
    monkeypatch.setitem(client.application.view_functions, endpoint, handler)

    def deliver(method: str, url: str, **kwargs: Any) -> Response:
        assert urlparse(url).hostname == "192.0.2.42"
        assert kwargs["headers"]["X-Pioreactor-Target"] == target
        response = client.open(urlparse(url).path, method=method, headers=kwargs["headers"])
        return Response(url, response.status_code, dict(response.headers), response.data)

    monkeypatch.setattr("pioreactor.mureq.request", deliver)
    unit, result = getattr(tasks, task_name).call_local(target, path)

    assert unit == target
    assert result["ok"] is (target == HOSTNAME)
    if target == HOSTNAME:
        handler.assert_called_once()
    else:
        handler.assert_not_called()
        assert result["status_code"] == 409
        assert result["retryable"] is False


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("DELETE", "/api/workers/unit1/camera/experiments/exp1/stills/image.jpg", None),
        ("PATCH", "/api/workers/unit1/camera/experiments/exp1/stills/image.jpg", {"new_image_id": "new"}),
        ("PUT", "/api/config/units/unit1/specific", {"code": "[section]\nvalue=1\n"}),
        ("POST", "/api/workers/unit1/calibrations/sessions/session-id/abort", None),
    ],
)
def test_direct_proxy_supplies_intended_hostname(
    client: FlaskClient, method: str, path: str, payload: dict[str, str] | None
) -> None:
    with capture_requests() as requests:
        response = client.open(path, method=method, json=payload)

    assert response.status_code == 200
    assert len(requests) == 1
    assert requests[0].headers["X-Pioreactor-Target"] == "unit1"


def test_broadcast_sends_each_workers_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks.huey, "immediate", True)
    # A broadcast must retain distinct identities even when addresses collide.
    monkeypatch.setattr(tasks, "resolve_to_address", lambda unit: "192.0.2.42")
    with capture_requests() as requests:
        result = tasks.multicast_post("/unit_api/jobs/stop/all", ["worker-a", "worker-b"]).get()

    assert result["worker-a"]["ok"] is True
    assert result["worker-b"]["ok"] is True
    assert [request.headers["X-Pioreactor-Target"] for request in requests] == ["worker-a", "worker-b"]
