# -*- coding: utf-8 -*-
import json
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pioreactor.cli.pio import pio
from pioreactor.config import leader_address
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.unit_model import get_local_model


@pytest.mark.parametrize("json_output", [False, True])
def test_model_cli_roundtrip_and_validation(monkeypatch: pytest.MonkeyPatch, json_output: bool) -> None:
    monkeypatch.setattr("pioreactor.cli.model.check_model_hardware", Mock())
    report = Mock()
    monkeypatch.setattr("pioreactor.cli.model.report_model_to_leader", report)
    runner = CliRunner()
    result = runner.invoke(pio, ["model", "set", "unknown", "1.5"])
    assert result.exit_code != 0
    assert get_local_model() is None
    options = ["--json"] if json_output else []
    result = runner.invoke(pio, ["model", "set", "pioreactor_20ml", "1.5", *options])
    assert result.exit_code == 0, result.output
    if json_output:
        assert json.loads(result.output) == {"model_name": "pioreactor_20ml", "model_version": "1.5"}
    else:
        assert result.output == "Pioreactor 20ml, v1.5\n"
    assert runner.invoke(pio, ["model", "get", *options]).output == result.output
    assert get_local_model() == ("pioreactor_20ml", "1.5")
    report.assert_called_once_with(leader_address, "pioreactor_20ml", "1.5")


def test_workers_model_set_uses_positional_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    request = Mock(return_value=Response("http://leader/api/workers/unit1/model", 200, {}, b"{}"))
    monkeypatch.setattr("pioreactor.cluster_management.put_into_leader", request)

    result = CliRunner().invoke(pio, ["workers", "model", "set", "unit1", "pioreactor_40ml", "1.5"])

    assert result.exit_code == 0, result.output
    request.assert_called_once_with(
        "/api/workers/unit1/model", json={"model_name": "pioreactor_40ml", "model_version": "1.5"}
    )
    assert get_local_model() is None


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("display_name", [None, "Custom bench reactor"])
def test_workers_model_get_prints_assignment(
    monkeypatch: pytest.MonkeyPatch, json_output: bool, display_name: str | None
) -> None:
    request = Mock(
        return_value=Response(
            "http://leader/api/workers/unit1/model",
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "model_name": "custom_bench_reactor",
                    "model_version": "1.0",
                    "reactor_capacity_ml": 25.0,
                    "display_name": display_name,
                }
            ).encode(),
        )
    )
    monkeypatch.setattr("pioreactor.cluster_management.get_from_leader", request)

    options = ["--json"] if json_output else []
    result = CliRunner().invoke(pio, ["workers", "model", "get", "unit1", *options])

    assert result.exit_code == 0, result.output
    if json_output:
        assert json.loads(result.output) == {"model_name": "custom_bench_reactor", "model_version": "1.0"}
    else:
        assert result.output.strip() == (display_name or "custom_bench_reactor v1.0")
    request.assert_called_once_with("/api/workers/unit1/model")


@pytest.mark.parametrize("unreachable", [False, True])
def test_workers_model_get_reports_errors(monkeypatch: pytest.MonkeyPatch, unreachable: bool) -> None:
    request = Mock(
        return_value=Response(
            "http://leader/api/workers/unit1/model",
            404,
            {"Content-Type": "application/json"},
            b'{"error":"Model not set for worker unit1.","status":404}',
        ),
        side_effect=HTTPException("unreachable") if unreachable else None,
    )
    monkeypatch.setattr("pioreactor.cluster_management.get_from_leader", request)

    result = CliRunner().invoke(pio, ["workers", "model", "get", "unit1"])

    assert result.exit_code == 1
    message = "Not able to connect to leader's backend." if unreachable else "Model not set for worker unit1."
    assert message in result.output


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("assignment", [None, ("pioreactor_40ml", "1.5")])
def test_model_get_and_adopt_output(
    monkeypatch: pytest.MonkeyPatch, json_output: bool, assignment: tuple[str, str] | None
) -> None:
    monkeypatch.setattr("pioreactor.cli.model.get_local_model", Mock(return_value=assignment))
    monkeypatch.setattr("pioreactor.cli.model.adopt_leader_model", Mock(return_value=assignment))
    options = ["--json"] if json_output else []
    for command in ("get", "adopt"):
        result = CliRunner().invoke(pio, ["model", command, *options])
        assert result.exit_code == 0, result.output
        if json_output:
            model_name, model_version = assignment or (None, None)
            assert json.loads(result.output) == {"model_name": model_name, "model_version": model_version}
        else:
            assert result.output.strip() == ("Pioreactor 40ml, v1.5" if assignment else "No model assigned.")
