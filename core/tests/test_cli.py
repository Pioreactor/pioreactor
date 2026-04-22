# -*- coding: utf-8 -*-
# test_cli.py
import json
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import cast
from typing import Iterator

import click
import pytest
from click.testing import CliRunner
from pioreactor import bioreactor
from pioreactor import exc
from pioreactor import whoami
from pioreactor.background_jobs.dosing_automation import start_dosing_automation
from pioreactor.cli.pio import pio
from pioreactor.cli.pios import kill
from pioreactor.cli.pios import pios
from pioreactor.cli.pios import reboot
from pioreactor.cli.pios import run
from pioreactor.config import config
from pioreactor.config import get_config
from pioreactor.config import get_leader_hostname
from pioreactor.config import temporary_config_change
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.networking import resolve_to_address
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


def test_pio_mqtt_subscribes_with_exactly_once(monkeypatch) -> None:
    captured_args: list[str] = []

    class FakePopen:
        def __init__(self, args: list[str], **kwargs) -> None:
            captured_args.extend(args)
            self.stdout: Iterator[str] = iter([])

        def __enter__(self) -> "FakePopen":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    with temporary_config_change(config, "mqtt", "username", "custom-user"):
        with temporary_config_change(config, "mqtt", "password", "custom-password"):
            runner = CliRunner()
            result = runner.invoke(pio, ["mqtt", "-t", "pioreactor/unit/exp/dosing_events"])

    assert result.exit_code == 0
    assert captured_args == [
        "mosquitto_sub",
        "-v",
        "-t",
        "pioreactor/unit/exp/dosing_events",
        "-q",
        "2",
        "-F",
        "%19.19I||%t||%p",
        "-u",
        "custom-user",
        "-P",
        "custom-password",
    ]


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


def test_pio_config_get(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.delenv("GLOBAL_CONFIG", raising=False)
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "get", "mqtt", "broker_address"])
        assert result.exit_code == 0
        assert result.output == "local-broker\n"
    finally:
        get_config.cache_clear()


def test_pio_config_get_shared_reads_only_shared_file(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setenv("GLOBAL_CONFIG", str(tmp_path / "config.ini"))
    monkeypatch.setenv("LOCAL_CONFIG", str(tmp_path / "unit_config.ini"))
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "get", "mqtt", "broker_address", "--shared"])
        assert result.exit_code == 0
        assert result.output == "global-broker\n"
    finally:
        get_config.cache_clear()


def test_pio_config_get_specific_reads_only_specific_file(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setenv("GLOBAL_CONFIG", str(tmp_path / "config.ini"))
    monkeypatch.setenv("LOCAL_CONFIG", str(tmp_path / "unit_config.ini"))
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "get", "mqtt", "broker_address", "--specific"])
        assert result.exit_code == 0
        assert result.output == "local-broker\n"
    finally:
        get_config.cache_clear()


def test_pio_config_get_missing_key(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.delenv("GLOBAL_CONFIG", raising=False)
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "get", "mqtt", "missing"])
        assert result.exit_code != 0
        assert "Key 'missing' not found in section 'mqtt'." in result.output
    finally:
        get_config.cache_clear()


def test_pio_config_get_shared_missing_derived_section_errors(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[PWM]
0=stirring
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setenv("GLOBAL_CONFIG", str(tmp_path / "config.ini"))
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "get", "PWM_reverse", "stirring", "--shared"])
        assert result.exit_code != 0
        assert "Section 'PWM_reverse' not found in config file." in result.output
    finally:
        get_config.cache_clear()


def test_pio_config_get_rejects_both_targets(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setenv("GLOBAL_CONFIG", str(tmp_path / "config.ini"))
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        pio,
        ["config", "get", "mqtt", "broker_address", "--shared", "--specific"],
    )
    assert result.exit_code != 0
    assert "Specify at most one of --shared or --specific." in result.output


def test_pio_config_set_specific_updates_unit_config(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "unit_config.ini").write_text(
        """
[mqtt]
broker_address=local-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.delenv("GLOBAL_CONFIG", raising=False)
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(
            pio, ["config", "set", "mqtt", "broker_address", "updated-broker", "--specific"]
        )
        assert result.exit_code == 0
        assert "broker_address=updated-broker" in (tmp_path / "unit_config.ini").read_text(encoding="utf-8")

        result = runner.invoke(pio, ["config", "get", "mqtt", "broker_address"])
        assert result.exit_code == 0
        assert result.output == "updated-broker\n"
    finally:
        get_config.cache_clear()


def test_pio_config_set_preserves_existing_file_mode(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local

[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )
    config_path.chmod(0o664)

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setenv("GLOBAL_CONFIG", str(config_path))
    monkeypatch.delenv("LOCAL_CONFIG", raising=False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "set", "mqtt", "broker_address", "updated-broker", "--shared"])
        assert result.exit_code == 0
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o664
    finally:
        get_config.cache_clear()


def test_pio_config_set_specific_creates_missing_section(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[cluster.topology]
leader_hostname=leader
leader_address=leader.local
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(
            pio,
            ["config", "set", "new.section", "new_key", "new_value", "--specific"],
        )
        assert result.exit_code == 0
        assert "[new.section]" in (tmp_path / "unit_config.ini").read_text(encoding="utf-8")

        result = runner.invoke(pio, ["config", "get", "new.section", "new_key"])
        assert result.exit_code == 0
        assert result.output == "new_value\n"
    finally:
        get_config.cache_clear()


def test_pio_config_set_shared_is_noop_if_not_leader(tmp_path: Path, monkeypatch) -> None:
    original_shared_text = """
[mqtt]
broker_address=global-broker
""".strip()
    (tmp_path / "config.ini").write_text(original_shared_text, encoding="utf-8")

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    monkeypatch.setattr("pioreactor.cli.pio.whoami.am_I_leader", lambda: False)
    get_config.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(pio, ["config", "set", "mqtt", "broker_address", "updated-broker", "--shared"])
        assert result.exit_code == 0
        assert (tmp_path / "config.ini").read_text(encoding="utf-8") == original_shared_text
    finally:
        get_config.cache_clear()


def test_pio_config_set_requires_exactly_one_target(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.ini").write_text(
        """
[mqtt]
broker_address=global-broker
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(pio, ["config", "set", "mqtt", "broker_address", "updated-broker"])
    assert result.exit_code != 0
    assert "Specify exactly one of --shared or --specific." in result.output

    result = runner.invoke(
        pio,
        ["config", "set", "mqtt", "broker_address", "updated-broker", "--shared", "--specific"],
    )
    assert result.exit_code != 0
    assert "Specify exactly one of --shared or --specific." in result.output


def test_pio_config_shortcut_lookup_is_not_supported() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["config", "mqtt", "broker_address"])
    assert result.exit_code != 0
    assert "No such command 'mqtt'." in result.output


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


def test_pio_status_handles_unassigned_experiment(monkeypatch) -> None:
    def raise_not_assigned(_unit: str) -> str:
        raise exc.NotAssignedAnExperimentError("no experiment assigned")

    monkeypatch.setattr("pioreactor.whoami.get_assigned_experiment_name", raise_not_assigned)

    runner = CliRunner()
    result = runner.invoke(pio, ["status"])

    assert result.exit_code == 0
    identity_line = next(line for line in result.output.splitlines() if line.startswith("identity"))
    assert "OK" in identity_line
    assert "experiment=" in identity_line
    assert whoami.NO_EXPERIMENT not in identity_line
    assert "worker is not assigned to an experiment" not in result.output


def test_pio_status_handles_internal_errors_without_aborting(monkeypatch) -> None:
    def raise_unit_name() -> str:
        raise RuntimeError("unit lookup failed")

    def raise_is_worker() -> bool:
        raise RuntimeError("worker lookup failed")

    def raise_config(*_args, **_kwargs):
        raise RuntimeError("config unavailable")

    class BrokenJobManager:
        def __enter__(self):
            raise RuntimeError("job manager unavailable")

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("pioreactor.whoami.get_unit_name", raise_unit_name)
    monkeypatch.setattr("pioreactor.whoami.am_I_a_worker", raise_is_worker)
    monkeypatch.setattr("pioreactor.pubsub.create_webserver_path", raise_config)
    monkeypatch.setattr("pioreactor.config.config.get", raise_config)
    monkeypatch.setattr("pioreactor.config.config.getint", raise_config)
    monkeypatch.setattr("pioreactor.utils.job_manager.JobManager", BrokenJobManager)

    runner = CliRunner()
    result = runner.invoke(pio, ["status"])

    assert result.exit_code == 0
    assert "identity" in result.output
    assert "services:web" in result.output
    assert "jobs:running" in result.output
    assert "job manager unavailable" in result.output


def test_pio_status_handles_i2c_scan_errors_without_aborting(monkeypatch) -> None:
    def raise_i2c_error(*_args, **_kwargs) -> None:
        raise RuntimeError("i2c unavailable")

    monkeypatch.setattr("pioreactor.utils.mock.MockI2C.writeto", raise_i2c_error)

    runner = CliRunner()
    result = runner.invoke(pio, ["status"])

    assert result.exit_code == 0
    i2c_line = next(line for line in result.output.splitlines() if line.startswith("hardware:i2c_bus1"))
    assert "WARN" in i2c_line
    assert "scan failed (i2c unavailable)" in i2c_line


def test_pio_cache_view_without_key_shows_all_keys() -> None:
    cache_name = "test_pio_cache_view_without_key_shows_all_keys"

    try:
        with local_intermittent_storage(cache_name) as c:
            c["b"] = "intermittent_b"
            c["a"] = "intermittent_a"

        with local_persistent_storage(cache_name) as c:
            c["c"] = "persistent_c"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "view", cache_name])

        assert result.exit_code == 0
        assert "a = intermittent_a" in result.output
        assert "b = intermittent_b" in result.output
        assert "c = persistent_c" in result.output
    finally:
        with local_intermittent_storage(cache_name) as c:
            for key in tuple(c.iterkeys()):
                del c[key]
        with local_persistent_storage(cache_name) as c:
            for key in tuple(c.iterkeys()):
                del c[key]


def test_pio_cache_view_handles_tuple_keys() -> None:
    experiment = "test_pio_cache_view_handles_tuple_keys"

    try:
        bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 12.5)
        bioreactor.set_bioreactor_value(experiment, "alt_media_fraction", 0.3)

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "view", "bioreactor"])

        assert result.exit_code == 0
        assert "('test_pio_cache_view_handles_tuple_keys', 'alt_media_fraction') = 0.3" in result.output
        assert "('test_pio_cache_view_handles_tuple_keys', 'current_volume_ml') = 12.5" in result.output
    finally:
        with local_persistent_storage("bioreactor") as c:
            c.pop((experiment, "current_volume_ml"), None)
            c.pop((experiment, "alt_media_fraction"), None)


def test_pio_cache_view_with_key_filters_integer_keys() -> None:
    cache_name = "test_pio_cache_view_with_key_filters_integer_keys"

    try:
        with local_persistent_storage(cache_name) as c:
            c[12] = "twelve"
            c[13] = "thirteen"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "view", cache_name, "12"])

        assert result.exit_code == 0
        assert "12 = twelve" in result.output
        assert "13 = thirteen" not in result.output
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop(12, None)
            c.pop(13, None)


def test_pio_cache_view_with_key_filters_tuple_keys() -> None:
    cache_name = "test_pio_cache_view_with_key_filters_tuple_keys"

    try:
        with local_persistent_storage(cache_name) as c:
            c[("a", "b")] = "first"
            c[("c", "d")] = "second"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "view", cache_name, "('a', 'b')"])

        assert result.exit_code == 0
        assert "('a', 'b') = first" in result.output
        assert "('c', 'd') = second" not in result.output
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop(("a", "b"), None)
            c.pop(("c", "d"), None)


def test_pio_cache_purge_with_key_removes_tuple_keys() -> None:
    cache_name = "test_pio_cache_purge_with_key_removes_tuple_keys"

    try:
        with local_persistent_storage(cache_name) as c:
            c[("a", "b")] = "first"
            c[("c", "d")] = "second"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "purge", cache_name, "('a', 'b')"])

        assert result.exit_code == 0
        assert "Removed key ('a', 'b')" in result.output

        with local_persistent_storage(cache_name) as c:
            assert ("a", "b") not in c
            assert ("c", "d") in c
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop(("a", "b"), None)
            c.pop(("c", "d"), None)


def test_pio_cache_purge_prefers_raw_string_key_over_parsed_literal() -> None:
    cache_name = "test_pio_cache_purge_prefers_raw_string_key_over_parsed_literal"

    try:
        with local_persistent_storage(cache_name) as c:
            c["12"] = "string-twelve"
            c[12] = "int-twelve"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "purge", cache_name, "12"])

        assert result.exit_code == 0
        assert "Removed key 12" in result.output

        with local_persistent_storage(cache_name) as c:
            assert "12" not in c
            assert 12 in c
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop("12", None)
            c.pop(12, None)


def test_pio_cache_purge_falls_back_to_parsed_literal_when_raw_string_missing() -> None:
    cache_name = "test_pio_cache_purge_falls_back_to_parsed_literal_when_raw_string_missing"

    try:
        with local_persistent_storage(cache_name) as c:
            c[12] = "int-twelve"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "purge", cache_name, "12"])

        assert result.exit_code == 0
        assert "Removed key 12" in result.output

        with local_persistent_storage(cache_name) as c:
            assert 12 not in c
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop(12, None)


def test_pio_cache_purge_prefers_raw_string_boolean_like_keys() -> None:
    cache_name = "test_pio_cache_purge_prefers_raw_string_boolean_like_keys"

    try:
        with local_persistent_storage(cache_name) as c:
            c["True"] = "string-true"
            c[True] = "bool-true"

        runner = CliRunner()
        result = runner.invoke(pio, ["cache", "purge", cache_name, "True"])

        assert result.exit_code == 0
        assert "Removed key True" in result.output

        with local_persistent_storage(cache_name) as c:
            assert "True" not in c
            assert True in c
    finally:
        with local_persistent_storage(cache_name) as c:
            c.pop("True", None)
            c.pop(True, None)


def test_led_intensity() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["run", "led_intensity", "--A", "1"])
    assert result.exit_code == 0
    with local_intermittent_storage("leds") as c:
        assert float(cast(float, c["A"])) == 1.0


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


def test_pio_update_settings_requires_key_value_pairs() -> None:
    runner = CliRunner()
    result = runner.invoke(pio, ["update-settings", "stirring", "--target-rpm"])

    assert result.exit_code != 0
    assert "Settings must be provided as --key value pairs." in result.output


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


def test_pios_run_requests_with_config_override() -> None:
    runner = CliRunner()
    with capture_requests() as bucket:
        result = runner.invoke(
            pios,
            [
                "run",
                "stirring",
                "--config-override",
                "stirring.config",
                "pwm_hz",
                "100",
                "-y",
            ],
        )

    assert result.exit_code == 0
    assert len(bucket) == 2
    assert all(
        req.json == {"args": [], "options": {}, "config_overrides": [["stirring.config", "pwm_hz", "100"]]}
        for req in bucket
    )


def test_pios_update_requests_with_sha() -> None:
    runner = CliRunner()
    git_sha = "a0b1c2d3"
    with capture_requests() as bucket:
        result = runner.invoke(pios, ["update", "--sha", git_sha, "-y"])

    assert result.exit_code == 0
    update_requests = [req for req in bucket if req.path == "/unit_api/system/update/app"]
    assert len(update_requests) >= 3
    update_urls = {req.url for req in update_requests}
    assert (
        f"http://{resolve_to_address(get_leader_hostname())}:4999/unit_api/system/update/app" in update_urls
    )
    assert "http://unit1.local:4999/unit_api/system/update/app" in update_urls
    assert "http://unit2.local:4999/unit_api/system/update/app" in update_urls
    assert all(req.json == {"options": {"sha": git_sha}} for req in update_requests)


def test_pios_update_app_requests_with_sha() -> None:
    runner = CliRunner()
    git_sha = "a0b1c2d3"
    with capture_requests() as bucket:
        result = runner.invoke(pios, ["update", "app", "--sha", git_sha, "-y"])

    assert result.exit_code == 0
    update_requests = [req for req in bucket if req.path == "/unit_api/system/update/app"]
    assert len(update_requests) >= 3
    update_urls = {req.url for req in update_requests}
    assert (
        f"http://{resolve_to_address(get_leader_hostname())}:4999/unit_api/system/update/app" in update_urls
    )
    assert "http://unit1.local:4999/unit_api/system/update/app" in update_urls
    assert "http://unit2.local:4999/unit_api/system/update/app" in update_urls
    assert all(req.json == {"options": {"sha": git_sha}} for req in update_requests)


def test_pios_rejects_combining_units_and_experiments() -> None:
    runner = CliRunner()

    result = runner.invoke(
        pios,
        ["run", "--units", "unit1", "--experiments", "exp1", "stirring", "-y"],
    )

    assert result.exit_code != 0
    assert "Use either --units or --experiments, not both" in result.output


def test_pios_rejects_unknown_explicit_units() -> None:
    runner = CliRunner()

    result = runner.invoke(
        pios,
        ["run", "--units", "unknown-unit", "stirring", "-y"],
    )

    assert result.exit_code != 0
    assert "Unknown unit(s): unknown-unit" in result.output


def test_pios_update_app_ssh_fallback_includes_repo(monkeypatch) -> None:
    from pioreactor.mureq import HTTPException

    runner = CliRunner()
    commands: list[str] = []

    def fail_post_into(*_args, **_kwargs):
        raise HTTPException("worker webserver unavailable")

    def record_ssh(_address: str, command: str) -> None:
        commands.append(command)

    monkeypatch.setattr("pioreactor.cli.pios.post_into", fail_post_into)
    monkeypatch.setattr("pioreactor.cli.pios.ssh", record_ssh)

    result = runner.invoke(
        pios,
        ["update", "app", "--version", "1.2.3", "--repo", "org/repo", "-y"],
    )

    assert result.exit_code == 0
    assert len(commands) >= 1
    assert all("--repo org/repo" in command for command in commands)


def test_pios_update_alias_ssh_fallback_includes_repo(monkeypatch) -> None:
    from pioreactor.mureq import HTTPException

    runner = CliRunner()
    commands: list[str] = []

    def fail_post_into(*_args, **_kwargs):
        raise HTTPException("worker webserver unavailable")

    def record_ssh(_address: str, command: str) -> None:
        commands.append(command)

    monkeypatch.setattr("pioreactor.cli.pios.post_into", fail_post_into)
    monkeypatch.setattr("pioreactor.cli.pios.ssh", record_ssh)

    result = runner.invoke(
        pios,
        ["update", "--version", "1.2.3", "--repo", "org/repo", "-y"],
    )

    assert result.exit_code == 0
    assert len(commands) >= 1
    assert all(command.startswith("pio update app ") for command in commands)
    assert all("--repo org/repo" in command for command in commands)


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


def test_pios_jobs_list_partitions_output_by_unit(monkeypatch) -> None:
    class DummyResponse:
        def __init__(self, payload: list[dict[str, str | int | None]]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return

        def json(self) -> list[dict[str, str | int | None]]:
            return self._payload

    responses = {
        "unit1.local": DummyResponse(
            [
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
        ),
        "unit2.local": DummyResponse(
            [
                {
                    "job_id": 43,
                    "job_name": "od_reading",
                    "experiment": "_testing_experiment",
                    "job_source": "cli",
                    "unit": "unit2",
                    "started_at": "2026-01-01T00:05:00.000Z",
                    "ended_at": None,
                }
            ]
        ),
    }

    def fake_get_from(address: str, endpoint: str, **_kwargs):
        assert endpoint == "/unit_api/jobs"
        return responses[address]

    monkeypatch.setattr("pioreactor.cli.pios.get_from", fake_get_from)

    runner = CliRunner()
    result = runner.invoke(pios, ["jobs", "list", "--units", "unit1", "--units", "unit2"])
    assert result.exit_code == 0

    lines = result.output.splitlines()
    assert "unit1" in lines
    assert "unit2" in lines
    assert "  [job_id=42]" in result.output
    assert "  [job_id=43]" in result.output
    unit1_job_line = next(line for line in lines if "[job_id=42]" in line)
    unit2_job_line = next(line for line in lines if "[job_id=43]" in line)
    assert lines.index("unit1") < lines.index(unit1_job_line)
    assert lines.index("unit2") < lines.index(unit2_job_line)


def test_pios_sync_configs_specific_refreshes_unit_snapshots(monkeypatch, tmp_path: Path) -> None:
    from pioreactor.mureq import Response
    from pioreactor.config import config

    db_path = tmp_path / "app.sqlite"
    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "unit_config.ini").write_text("[leader]\nvalue=1\n", encoding="utf-8")

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE config_files_histories(timestamp TEXT, filename TEXT, data TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    monkeypatch.setattr("pioreactor.cli.pios.get_leader_hostname", lambda: "leader")
    monkeypatch.setattr(
        "pioreactor.cli.pios.get_from",
        lambda address, endpoint, **_kwargs: Response(
            f"http://{address}:4999{endpoint}",
            200,
            {},
            b"[remote]\nvalue=2\n",
        ),
    )

    with temporary_config_change(config, "storage", "database", str(db_path)):
        runner = CliRunner()
        result = runner.invoke(pios, ["sync-configs", "--specific", "--units", "unit1", "-y"])
        assert result.exit_code == 0

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT filename, data FROM config_files_histories WHERE filename = ?",
        ("unit_config.ini::unit1",),
    ).fetchall()
    conn.close()

    assert rows == [("unit_config.ini::unit1", "[remote]\nvalue=2\n")]


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
