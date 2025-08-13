# -*- coding: utf-8 -*-
# test_cli.py
from __future__ import annotations

import time

import click
import pytest
from click.testing import CliRunner
from pioreactor import whoami
from pioreactor.background_jobs.dosing_automation import start_dosing_automation
from pioreactor.cli.pio import pio
from pioreactor.cli.pios import kill
from pioreactor.cli.pios import pios
from pioreactor.cli.pios import reboot
from pioreactor.cli.pios import run
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage
from tests.conftest import capture_requests


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
    assert "my-example-plugin==0.2.0" in result.output


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

    def put_into_bucket(msg) -> None:
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
        result = runner.invoke(pio, ["kill", "--job-name", "dosing_automation"])

        pause()
        assert result.exit_code == 0
        pause()
        pause()
        pause()

        assert not is_pio_job_running("dosing_automation")


def test_pios_run_requests() -> None:
    with capture_requests() as bucket:
        ctx = click.Context(run, allow_extra_args=True)
        ctx.forward(run, job="stirring", y=True)

    assert len(bucket) == 2
    assert sorted(bucket)[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/stirring"


def test_pios_run_requests_dedup() -> None:
    units = ("unit1", "unit1")

    with capture_requests() as bucket:
        ctx = click.Context(run, allow_extra_args=True)
        ctx.forward(run, job="stirring", y=True, units=units)

    assert len(bucket) == 1
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/stirring"


def test_pios_run_requests_with_experiments(active_workers_in_cluster):
    runner = CliRunner()
    with capture_requests() as bucket:
        result = runner.invoke(pios, ["run", "--experiments", "exp1", "stirring", "-y"])
    assert result.exit_code == 0

    expected_urls = [
        f"http://{unit}.local:4999/unit_api/jobs/run/job_name/stirring" for unit in active_workers_in_cluster
    ]
    assert sorted(req.url for req in bucket) == sorted(expected_urls)


def test_pios_kill_requests() -> None:
    with capture_requests() as bucket:
        ctx = click.Context(kill, allow_extra_args=True)
        ctx.forward(kill, experiment="demo", y=True)

    assert len(bucket) == 2
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/stop"
    assert bucket[0].params == {"experiment": "demo"}
    assert bucket[1].url == "http://unit2.local:4999/unit_api/jobs/stop"
    assert bucket[1].params == {"experiment": "demo"}


def test_pios_kill_requests_with_experiments(active_workers_in_cluster):
    runner = CliRunner()
    with capture_requests() as bucket:
        result = runner.invoke(pios, ["kill", "--all-jobs", "--experiments", "exp1", "-y"])
    assert result.exit_code == 0

    for req in bucket:
        assert req.url.endswith("/unit_api/jobs/stop/all")
        assert req.params == {}


def test_pios_run_fails_when_no_workers_for_experiment(monkeypatch):
    # simulate no workers assigned to experiment
    # override callback import in CLI to simulate no experiment assignments
    monkeypatch.setattr("pioreactor.cli.pios.get_active_workers_in_experiment", lambda exp: [])
    runner = CliRunner()
    result = runner.invoke(pios, ["run", "--experiments", "wrong-exp", "stirring", "-y"])
    assert result.exit_code != 0
    assert "No active workers found for experiment(s): wrong-exp" in result.output


def test_pios_reboot_requests() -> None:
    with capture_requests() as bucket:
        ctx = click.Context(reboot, allow_extra_args=True)
        ctx.forward(reboot, y=True, units=("unit1",))

    assert len(bucket) == 1
    assert bucket[0].url == "http://unit1.local:4999/unit_api/system/reboot"
