# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from click.testing import CliRunner
from pioreactor import calibrations as calibrations_module
from pioreactor.cli import calibrations as cli_calibrations


def test_list_calibrations_reports_unreadable_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(calibrations_module, "CALIBRATION_PATH", tmp_path)
    monkeypatch.setattr(cli_calibrations, "CALIBRATION_PATH", tmp_path)
    (tmp_path / "od90").mkdir()
    (tmp_path / "od90" / "broken.yaml").write_text("calibration_name: [\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli_calibrations.list_calibrations, ["--device", "od90"])

    assert "Error reading od90 calibration `broken`" in click.unstyle(result.output)
