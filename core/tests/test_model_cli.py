# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pioreactor.cli.pio import pio
from pioreactor.config import leader_address
from pioreactor.unit_model import get_local_model


def test_model_cli_roundtrip_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pioreactor.web.tasks.check_model_hardware", Mock())
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


def test_worker_ssh_setup_script_update_copy_matches_and_hides_password() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh"
    payload = root / "core/update_scripts/upcoming/add_new_pioreactor_worker_from_leader.sh"
    assert source.read_bytes() == payload.read_bytes()
    # xtrace would print the password into the logs that `pio workers add` publishes.
    assert "set -x" not in source.read_text()
    assert "sshpass -p" not in source.read_text()
