# -*- coding: utf-8 -*-
from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient
from pioreactor.web import api


@pytest.mark.parametrize("expected_step_id", ["stabilize", None])
def test_advance_session_forwards_step_guard(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, expected_step_id: str | None
) -> None:
    worker_response = Mock(
        status_code=202,
        content=b'{"task_id":"advance-1"}',
        headers={"Content-Type": "application/json"},
    )
    forward = Mock(return_value=worker_response)
    monkeypatch.setattr(api, "post_into_unit", forward)
    body: dict[str, object] = {"inputs": {}}
    if expected_step_id is not None:
        body["expected_step_id"] = expected_step_id

    response = client.post("/api/workers/unit1/calibrations/sessions/session-1/inputs", json=body)

    assert response.status_code == 202
    assert response.get_json() == {"task_id": "advance-1"}
    assert forward.call_args.kwargs["json"]["inputs"] == {}
    assert forward.call_args.kwargs["json"].get("expected_step_id") == expected_step_id
    assert forward.call_args.args[1] == "/unit_api/calibrations/sessions/session-1/inputs"


def test_advance_session_rejects_invalid_step_guard(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    forward = Mock()
    monkeypatch.setattr(api, "post_into_unit", forward)
    response = client.post(
        "/api/workers/unit1/calibrations/sessions/session-1/inputs",
        json={"inputs": {}, "expected_step_id": 123},
    )
    assert response.status_code == 400
    forward.assert_not_called()
