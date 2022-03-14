# -*- coding: utf-8 -*-
# test_cli.py
from __future__ import annotations

from click.testing import CliRunner

from pioreactor.cli.pio import pio
from pioreactor.utils import local_intermittent_storage


def test_run_exits_if_command_not_found():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "no_command"])
    assert result.exit_code == 2


def test_run():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "add_media", "--duration", "1"])
    assert result.exit_code == 0


def test_led_intensity():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "led_intensity", "--A", "1"])
    assert result.exit_code == 0
    with local_intermittent_storage("leds") as c:
        assert float(c["A"]) == 1.0


def test_plugin_is_available_to_run():
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "example_plugin"])
    assert result.exit_code == 0


def test_plugin_is_able_to_be_run():

    runner = CliRunner()
    result = runner.invoke(pio, ["run", "example_plugin"])
    assert result.exit_code == 0


def test_list_plugins():

    runner = CliRunner()
    result = runner.invoke(pio, ["list-plugins"])
    assert "example_plugin==0.0.1" in result.output
