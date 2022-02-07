# -*- coding: utf-8 -*-
# test_cli.py
from __future__ import annotations

from click.testing import CliRunner

from pioreactor.cli.pio import pio


def test_run_exits_if_command_not_found():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "no_command"])
    assert result.exit_code == 2


def test_run():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "add_media", "--duration", "1"])
    assert result.exit_code == 0


def test_plugin_is_available():

    runner = CliRunner()
    result = runner.invoke(pio, ["run", "example_plugin"])
    assert result.exit_code == 0
