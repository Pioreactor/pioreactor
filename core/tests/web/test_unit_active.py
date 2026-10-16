# -*- coding: utf-8 -*-
import json
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from flask.testing import FlaskClient
from pioreactor import whoami
from pioreactor.cli.pio import pio
from pioreactor.config import leader_address
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.unit_active import is_locally_active
from pioreactor.unit_active import save_local_active
from pioreactor.web import tasks


@pytest.fixture
def unit_tasks(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    mocks = {"kill": Mock(), "report": Mock()}
    monkeypatch.setattr(tasks, "kill_jobs_task", mocks["kill"])
    monkeypatch.setattr(tasks, "report_active_to_leader", mocks["report"])
    return mocks


def leader_is_active(client: FlaskClient, unit: str) -> int:
    return client.get(f"/api/workers/{unit}").get_json()["is_active"]


def test_unit_boots_active_until_deactivated() -> None:
    unit = whoami.get_unit_name()
    assert whoami.is_active(unit)

    save_local_active(False, stop_activities=False)
    assert not whoami.is_active(unit)

    save_local_active(True)
    assert whoami.is_active(unit)


def test_unit_api_deactivate_stops_activities_and_reports(
    client: FlaskClient, unit_tasks: dict[str, Mock]
) -> None:
    assert client.get("/unit_api/active").get_json() == {"is_active": 1}

    assert client.put("/unit_api/active", json={"is_active": 0}).status_code == 200

    assert client.get("/unit_api/active").get_json() == {"is_active": 0}
    unit_tasks["kill"].assert_called_once_with(all_jobs=True)
    unit_tasks["report"].assert_called_once_with(False)

    assert client.put("/unit_api/active", json={"is_active": 1}).status_code == 200
    assert is_locally_active()
    unit_tasks["kill"].assert_called_once()


def test_unit_api_rejects_invalid_status(client: FlaskClient, unit_tasks: dict[str, Mock]) -> None:
    assert client.put("/unit_api/active", json={"is_active": 2}).status_code == 400
    assert client.put("/unit_api/active", json={}).status_code == 400
    assert is_locally_active()


@pytest.mark.parametrize("new_status", [0, 1])
def test_leader_forwards_to_unit_then_mirrors(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, new_status: int
) -> None:
    put = Mock(return_value=Response("http://unit", 200, {}, b"{}"))
    monkeypatch.setattr("pioreactor.web.api.put_into_unit", put)

    assert client.put("/api/workers/unit3/is_active", json={"is_active": new_status}).status_code == 200

    put.assert_called_once_with("unit3", "/unit_api/active", json={"is_active": new_status}, timeout=5)
    assert leader_is_active(client, "unit3") == new_status


def test_leader_keeps_mirror_when_unit_rejects(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    response = Response("http://unit", 400, {}, b'{"error":"bad","status":400}')
    monkeypatch.setattr("pioreactor.web.api.put_into_unit", Mock(return_value=response))

    assert client.put("/api/workers/unit3/is_active", json={"is_active": 0}).status_code == 400
    assert leader_is_active(client, "unit3") == 1


def test_leader_deactivates_unreachable_unit_on_mirror_only(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pioreactor.web.api.put_into_unit", Mock(side_effect=HTTPException("offline")))

    assert client.put("/api/workers/unit3/is_active", json={"is_active": 1}).status_code == 502
    assert leader_is_active(client, "unit3") == 1

    assert client.put("/api/workers/unit3/is_active", json={"is_active": 0}).status_code == 200
    assert leader_is_active(client, "unit3") == 0

    # The unit's own value wins when it reports.
    assert client.put("/api/workers/unit3/reported_active", json={"is_active": 1}).status_code == 200
    assert leader_is_active(client, "unit3") == 1


def test_reported_active_updates_only_the_mirror(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    forward = Mock(side_effect=AssertionError("must not forward to the unit"))
    monkeypatch.setattr("pioreactor.web.api.put_into_unit", forward)

    assert client.put("/api/workers/unit3/reported_active", json={"is_active": 0}).status_code == 200
    assert client.put("/api/workers/unit3/reported_active", json={"is_active": 0}).status_code == 200
    assert leader_is_active(client, "unit3") == 0
    assert client.put("/api/workers/not_a_worker/reported_active", json={"is_active": 0}).status_code == 400
    forward.assert_not_called()


@pytest.mark.parametrize("json_output", [False, True])
def test_active_cli_roundtrip(monkeypatch: pytest.MonkeyPatch, json_output: bool) -> None:
    report = Mock(return_value=True)
    monkeypatch.setattr("pioreactor.cli.active.report_active_to_leader", report)
    runner = CliRunner()

    options = ["--json"] if json_output else []
    assert runner.invoke(pio, ["active", "get", *options]).output.strip() == (
        '{"is_active": 1}' if json_output else "1"
    )
    result = runner.invoke(pio, ["active", "set", "0", *options])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == ('{"is_active": 0}' if json_output else "0")
    assert runner.invoke(pio, ["active", "get", *options]).output == result.output
    assert not is_locally_active()
    report.assert_called_once_with(leader_address, False)
    assert runner.invoke(pio, ["active", "set", "2"]).exit_code != 0


@pytest.mark.parametrize("json_output", [False, True])
def test_adopt_copies_leader_value(monkeypatch: pytest.MonkeyPatch, json_output: bool) -> None:
    get = Mock(return_value=Response("http://leader", 200, {}, b'{"is_active": 0}'))
    monkeypatch.setattr("pioreactor.pubsub.get_from_leader", get)

    options = ["--json"] if json_output else []
    result = CliRunner().invoke(pio, ["active", "adopt", *options])
    assert result.exit_code == 0, result.output
    if json_output:
        assert json.loads(result.output) == {"is_active": 0}
    else:
        assert result.output.strip() == "0"
    assert not is_locally_active()
