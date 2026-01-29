# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from click.testing import CliRunner
from pioreactor import estimators as estimators_module
from pioreactor.cli import estimators as cli_estimators


def _patch_estimator_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(estimators_module, "ESTIMATOR_PATH", tmp_path)
    monkeypatch.setattr(cli_estimators, "ESTIMATOR_PATH", tmp_path)


def test_list_estimators_missing_device_prints_error(monkeypatch, tmp_path) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(cli_estimators.list_estimators, ["--device", "od_fused"])

    output = click.unstyle(result.output)
    assert "No estimators found for device 'od_fused'" in output


def test_delete_estimator_missing_file_aborts(monkeypatch, tmp_path) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        cli_estimators.delete_estimator,
        ["--device", "od_fused", "--name", "missing"],
        input="y\n",
    )

    output = click.unstyle(result.output)
    assert result.exit_code != 0
    assert "No such estimator file" in output
