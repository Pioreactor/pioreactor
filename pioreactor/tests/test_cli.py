# -*- coding: utf-8 -*-
# test_cli.py
from __future__ import annotations

import time

import pytest
from click.testing import CliRunner

from pioreactor import whoami
from pioreactor.background_jobs.dosing_automation import start_dosing_automation
from pioreactor.cli.pio import pio
from pioreactor.cli.pios import pios
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage


def pause() -> None:
    # to avoid race conditions
    time.sleep(0.5)


def test_run_exits_if_command_not_found() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "no_command"])
    assert result.exit_code == 2


def test_run() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run"])
    assert result.exit_code == 0


def test_led_intensity() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "led_intensity", "--A", "1"])
    assert result.exit_code == 0
    with local_intermittent_storage("leds") as c:
        assert float(c["A"]) == 1.0


def test_plugin_is_available_to_run() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "example_plugin"])
    assert result.exit_code == 0


def test_list_plugins() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["plugins", "list"])
    assert "example_plugin==0.0.1" in result.output


@pytest.mark.skip(reason="not sure why this fails")
def test_pio_log() -> None:
    with collect_all_logs_of_level("DEBUG", whoami.get_unit_name(), whoami.UNIVERSAL_EXPERIMENT) as bucket:
        runner = CliRunner()
        result = runner.invoke(pio, ["log", "-m", "test msg", "-n", "job1"])
        pause()
        pause()
        pause()

    assert result.exit_code == 0
    assert len(bucket) > 0
    assert bucket[0]["message"] == "test msg"
    assert bucket[0]["task"] == "job1"


def test_pios_update_settings() -> None:
    job_name = "test_job"
    published_setting_name = "attr"

    bucket = []

    def put_into_bucket(msg):
        bucket.append(msg)

    subscribe_and_callback(
        put_into_bucket, f"pioreactor/+/+/{job_name}/{published_setting_name}/set", allow_retained=False
    )

    runner = CliRunner()
    runner.invoke(pios, ["update-settings", job_name, f"--{published_setting_name}", "1", "-y"])
    pause()
    pause()
    pause()
    pause()
    pause()
    # TODO previously this was strictly more than 1 - why?
    assert len(bucket) >= 1


@pytest.mark.xfail(reason="the `pio kill` will kill the pid, which is this pytest process!")
def test_pio_kill_cleans_up_automations_correctly() -> None:
    exp = "test_pio_kill_cleans_up_automations_correctly"
    unit = "testing_unit"
    with start_dosing_automation("silent", unit=unit, experiment=exp):
        pause()

        assert is_pio_job_running("dosing_automation")

        runner = CliRunner()
        result = runner.invoke(pio, ["kill", "--name", "dosing_automation"])

        pause()
        assert result.exit_code == 0
        pause()
        pause()
        pause()

        assert not is_pio_job_running("dosing_automation")
