# -*- coding: utf-8 -*-
# test_cli.py
import json
import re
import time
from pathlib import Path

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
from pioreactor.config import get_config
from pioreactor.config import get_leader_hostname
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.job_manager import JobManager
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


def test_pio_config_show_json_with_sources(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker

[PWM]
0=stirring
""".strip()
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip()
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "show", "--json", "--with-source"])
        assert result.exit_code == 0

        payload = json.loads(result.output)
        assert payload["mqtt"]["broker_address"]["value"] == "local-broker"
        assert payload["mqtt"]["broker_address"]["source"] == "local"
        assert payload["cluster.topology"]["leader_hostname"]["source"] == "global"
        assert payload["PWM_reverse"]["stirring"]["source"] == "derived"
    finally:
        get_config.cache_clear()


def test_pio_config_show_section_and_key_filter(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker
""".strip()
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip()
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(
            pio,
            ["config", "show", "--json", "--section", "mqtt", "--key", "broker_address"],
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == {"mqtt": {"broker_address": "local-broker"}}
    finally:
        get_config.cache_clear()


def test_pio_config_show_key_requires_section() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["config", "show", "--key", "broker_address"])
    assert result.exit_code != 0
    assert "--key requires --section." in result.output


def test_led_intensity() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "led_intensity", "--A", "1"])
    assert result.exit_code == 0
    with local_intermittent_storage("leds") as c:
        assert float(c["A"]) == 1.0


@pytest.mark.xfail
def test_plugin_is_available_to_run() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "example_plugin"])
    assert result.exit_code == 0


def test_list_plugins() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["plugins", "list"])
    assert "my-example-plugin==0.2.0" in result.output


@pytest.mark.flakey
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
        ctx.forward(run, job="stirring", yes=True)

    assert len(bucket) == 2
    assert sorted(bucket)[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/stirring"


def test_pios_run_requests_dedup() -> None:
    units = ("unit1", "unit1")

    with capture_requests() as bucket:
        ctx = click.Context(run, allow_extra_args=True)
        ctx.forward(run, job="stirring", yes=True, units=units)

    assert len(bucket) == 1
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/stirring"


def test_pios_run_requests_with_experiments(active_workers_in_cluster) -> None:
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
        ctx.forward(kill, experiment="demo", yes=True)

    assert len(bucket) == 2
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/stop"
    assert bucket[0].json == {"experiment": "demo"}
    assert bucket[1].url == "http://unit2.local:4999/unit_api/jobs/stop"
    assert bucket[1].json == {"experiment": "demo"}


def test_pios_jobs_list_requests_history_endpoint(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> list[dict[str, str | int | None]]:
            return [
                {
                    "job_id": 42,
                    "job_name": "stirring",
                    "experiment": "_testing_experiment",
                    "job_source": "cli",
                    "unit": "unit1",
                    "started_at": "2026-01-01T00:00:00.000Z",
                    "ended_at": "2026-01-01T00:10:00.000Z",
                }
            ]

    captured: list[tuple[str, str]] = []

    def fake_get_from(address: str, endpoint: str, **_kwargs):
        captured.append((address, endpoint))
        return DummyResponse()

    monkeypatch.setattr("pioreactor.cli.pios.get_from", fake_get_from)

    runner = CliRunner()
    result = runner.invoke(pios, ["jobs", "list", "--units", "unit1"])
    assert result.exit_code == 0
    assert captured == [("unit1.local", "/unit_api/jobs")]
    assert "[job_id=42]" in result.output
    assert "stirring" in result.output


def test_pios_jobs_list_running_requests_running_endpoint(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> list[dict[str, str | int | None]]:
            return [
                {
                    "job_id": 43,
                    "job_name": "od_reading",
                    "experiment": "_testing_experiment",
                    "job_source": "cli",
                    "unit": "unit1",
                    "started_at": "2026-01-01T00:00:00.000Z",
                    "ended_at": None,
                }
            ]

    captured: list[tuple[str, str]] = []

    def fake_get_from(address: str, endpoint: str, **_kwargs):
        captured.append((address, endpoint))
        return DummyResponse()

    monkeypatch.setattr("pioreactor.cli.pios.get_from", fake_get_from)

    runner = CliRunner()
    result = runner.invoke(pios, ["jobs", "list", "running", "--units", "unit1"])
    assert result.exit_code == 0
    assert captured == [("unit1.local", "/unit_api/jobs/running")]
    assert "[job_id=43]" in result.output
    assert "still running" in result.output


def test_pio_job_info_lists_job() -> None:
    runner = CliRunner()
    job_name = "test_job"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name,
            job_source="cli",
            pid=12345,
            leader=get_leader_hostname(),
            is_long_running_job=True,
        )

    try:
        result = runner.invoke(pio, ["jobs", "info", "--job-name", job_name])
        assert result.exit_code == 0
        assert job_name in result.output
        assert str(job_id) in result.output
    finally:
        with JobManager() as jm:
            jm.set_not_running(job_id)


def test_pio_job_list_lists_job() -> None:
    runner = CliRunner()
    job_name = "test_job_list"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name,
            job_source="cli",
            pid=98765,
            leader=get_leader_hostname(),
            is_long_running_job=True,
        )
        jm.set_not_running(job_id)

    result = runner.invoke(pio, ["jobs", "list"])

    assert result.exit_code == 0
    matching_lines = [line for line in result.output.splitlines() if f"[job_id={job_id}]" in line]
    assert matching_lines, result.output
    assert "started_at=" in matching_lines[0]
    assert "ended_at=" in matching_lines[0]
    assert "still running" not in matching_lines[0]


def test_pio_job_list_running_lists_running_job() -> None:
    runner = CliRunner()
    job_name_running = "test_job_list_running_active"
    job_name_stopped = "test_job_list_running_stopped"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        running_job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name_running,
            job_source="cli",
            pid=98766,
            leader=get_leader_hostname(),
            is_long_running_job=False,
        )
        stopped_job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name_stopped,
            job_source="cli",
            pid=98767,
            leader=get_leader_hostname(),
            is_long_running_job=False,
        )
        jm.set_not_running(stopped_job_id)

    try:
        result = runner.invoke(pio, ["jobs", "list", "running"])

        assert result.exit_code == 0
        running_lines = [line for line in result.output.splitlines() if f"[job_id={running_job_id}]" in line]
        stopped_lines = [line for line in result.output.splitlines() if f"[job_id={stopped_job_id}]" in line]

        assert running_lines, result.output
        assert not stopped_lines, result.output
        assert "started_at=" in running_lines[0]
        assert "ended_at=" in running_lines[0]
        assert "still running" in running_lines[0]
    finally:
        with JobManager() as jm:
            jm.set_not_running(running_job_id)


def test_pio_jobs_running_command_is_removed() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["jobs", "running"])
    assert result.exit_code != 0
    assert "No such command 'running'" in result.output


def test_pio_job_info_shows_metadata_and_settings() -> None:
    runner = CliRunner()
    job_name = "test_job_info"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name,
            job_source="cli",
            pid=112233,
            leader=get_leader_hostname(),
            is_long_running_job=False,
        )
        jm.upsert_setting(job_id, "speed", "fast")

    try:
        result = runner.invoke(pio, ["jobs", "info", "--job-id", str(job_id)])
        assert result.exit_code == 0
        assert job_name in result.output
        assert "status=running" in result.output
        assert "published settings" in result.output
        assert "speed=fast" in result.output
        speed_line = next(line for line in result.output.splitlines() if "speed=fast" in line)
        match = re.search(r"created_at=([^,]+), updated_at=([^)]+)\)", speed_line)
        assert match, speed_line
        created_ts, updated_ts = match.groups()
        assert "." not in created_ts
        assert "." not in updated_ts

        # via job-name lookup
        result_by_name = runner.invoke(pio, ["jobs", "info", "--job-name", job_name])
        assert result_by_name.exit_code == 0
        assert str(job_id) in result_by_name.output
        assert "status=running" in result_by_name.output
    finally:
        with JobManager() as jm:
            jm.set_not_running(job_id)


def test_pio_job_purge_deletes_finished_job() -> None:
    runner = CliRunner()
    job_name = "test_job_remove"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name,
            job_source="cli",
            pid=445566,
            leader=get_leader_hostname(),
            is_long_running_job=False,
        )
        jm.upsert_setting(job_id, "speed", "fast")
        jm.set_not_running(job_id)

    result = runner.invoke(pio, ["jobs", "purge", "--job-id", str(job_id)])
    assert result.exit_code == 0
    assert "Removed job record" in result.output

    # via job-name, should fail gracefully since job removed
    result_by_name = runner.invoke(pio, ["jobs", "purge", "--job-name", job_name])
    assert "No running job found with name" in result_by_name.output

    with JobManager() as jm:
        assert jm.get_job_info(job_id) is None
        assert jm.list_job_settings(job_id) == []


def test_job_manager_get_running_job_id() -> None:
    job_name = "test_get_running_job_id"
    unit = whoami.get_unit_name()
    experiment = whoami.UNIVERSAL_EXPERIMENT

    with JobManager() as jm:
        job_id = jm.register_and_set_running(
            unit=unit,
            experiment=experiment,
            job_name=job_name,
            job_source="cli",
            pid=123456,
            leader=get_leader_hostname(),
            is_long_running_job=False,
        )

        assert jm.get_running_job_id(job_name) == job_id
        jm.set_not_running(job_id)

    with JobManager() as jm:
        assert jm.get_running_job_id(job_name) is None


def test_pios_kill_requests_with_experiments(active_workers_in_cluster) -> None:
    runner = CliRunner()
    with capture_requests() as bucket:
        result = runner.invoke(pios, ["kill", "--all-jobs", "-y"])
    assert result.exit_code == 0

    for req in bucket:
        assert req.url.endswith("/unit_api/jobs/stop/all")


def test_pios_reboot_requests() -> None:
    with capture_requests() as bucket:
        ctx = click.Context(reboot, allow_extra_args=True)
        ctx.forward(reboot, yes=True, units=("unit1",))

    assert len(bucket) == 1
    assert bucket[0].url == "http://unit1.local:4999/unit_api/system/reboot"
