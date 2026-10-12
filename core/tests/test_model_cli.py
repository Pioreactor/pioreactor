# -*- coding: utf-8 -*-
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pioreactor.cli.pio import pio
from pioreactor.unit_model import get_local_model


def test_model_cli_roundtrip_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pioreactor.web.tasks.check_model_hardware", Mock())
    runner = CliRunner()
    result = runner.invoke(pio, ["model", "set", "unknown", "1.5"])
    assert result.exit_code != 0
    assert get_local_model() is None
    result = runner.invoke(pio, ["model", "set", "pioreactor_20ml", "1.5"])
    assert result.exit_code == 0, result.output
    assert runner.invoke(pio, ["model", "get"]).output == result.output
    assert get_local_model() == ("pioreactor_20ml", "1.5")


def test_provisioning_script_saves_before_reboot_and_update_copy_matches() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh"
    payload = root / "core/update_scripts/upcoming/add_new_pioreactor_worker_from_leader.sh"
    assert source.read_bytes() == payload.read_bytes()
    assert source.read_text().index("MODEL_JSON=$(ssh") < source.read_text().index("sudo reboot")
    assert "--no-reboot" not in source.read_text()


@pytest.mark.parametrize("outcome", ["success", "blocked"])
def test_setup_script_model_save_precedes_reboot(tmp_path: Path, outcome: str) -> None:
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    source = (root / "packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh").read_text()
    # Run the actual script's model/reboot stage with a fake SSH executable.
    # No real provisioning commands or network connections are made.
    stage = (
        "set -e\nexec 3>&1 1>&2\nADDRESS=unit.local\nMODEL_NAME=pioreactor_20ml\nMODEL_VERSION=1.5\n"
        + source[source.index("# Save the model before rebooting") :]
    )
    ssh = tmp_path / "ssh"
    ssh.write_text(
        """#!/bin/bash
if [[ "$*" == *"sudo reboot"* ]]; then
    echo reboot >> "$EVENTS"
    exit 255
fi
echo model >> "$EVENTS"
case "$OUTCOME" in
    success) echo '{"model_name":"pioreactor_20ml","model_version":"1.5"}';;
    blocked) echo 'Stop activities before changing the model.' >&2; exit 1;;
esac
"""
    )
    ssh.chmod(0o755)
    events = tmp_path / "events"
    result = subprocess.run(
        ["bash", "-c", stage],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "EVENTS": str(events),
            "OUTCOME": outcome,
        },
    )
    if outcome == "blocked":
        assert result.returncode == 1
        assert events.read_text().splitlines() == ["model"]
        assert "Stop activities" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert events.read_text().splitlines() == ["model", "reboot"]
        assert json.loads(result.stdout) == {"model_name": "pioreactor_20ml", "model_version": "1.5"}
