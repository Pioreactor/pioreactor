# -*- coding: utf-8 -*-
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pioreactor.cli.pio import pio
from pioreactor.config import leader_address
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.unit_model import get_local_model


def test_model_cli_roundtrip_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pioreactor.cli.model.check_model_hardware", Mock())
    report = Mock()
    monkeypatch.setattr("pioreactor.cli.model.report_model_to_leader", report)
    runner = CliRunner()
    result = runner.invoke(pio, ["model", "set", "unknown", "1.5"])
    assert result.exit_code != 0
    assert get_local_model() is None
    result = runner.invoke(pio, ["model", "set", "pioreactor_20ml", "1.5"])
    assert result.exit_code == 0, result.output
    assert runner.invoke(pio, ["model", "get"]).output == result.output
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


def test_workers_model_get_prints_assignment(monkeypatch: pytest.MonkeyPatch) -> None:
    request = Mock(
        return_value=Response(
            "http://leader/api/workers/unit1/model",
            200,
            {"Content-Type": "application/json"},
            b'{"model_name":"custom_bench_reactor","model_version":"1.0","reactor_capacity_ml":25.0}',
        )
    )
    monkeypatch.setattr("pioreactor.cluster_management.get_from_leader", request)

    result = CliRunner().invoke(pio, ["workers", "model", "get", "unit1"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"model_name": "custom_bench_reactor", "model_version": "1.0"}
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


def test_worker_ssh_setup_script_update_copy_matches_and_hides_password() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh"
    payload = root / "core/update_scripts/upcoming/add_new_pioreactor_worker_from_leader.sh"
    assert source.read_bytes() == payload.read_bytes()
    # xtrace would print the password into the logs that `pio workers add` publishes.
    assert "set -x" not in source.read_text()
    assert "sshpass -p" not in source.read_text()
