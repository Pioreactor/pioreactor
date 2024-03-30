# -*- coding: utf-8 -*-
# test_monitor
from __future__ import annotations

import time

from pioreactor.background_jobs.monitor import Monitor
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def pause(n=1):
    time.sleep(n * 0.5)


def test_check_job_states_in_monitor() -> None:
    unit = get_unit_name()
    exp = UNIVERSAL_EXPERIMENT

    # suppose od_reading is READY when monitor starts, but isn't actually running, ex after a reboot on a worker.
    publish(
        f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/od_reading/$state",
        "ready",
        retain=True,
    )

    with Monitor(unit=unit, experiment=exp):
        pause(20)
        message = subscribe(f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/od_reading/$state")
        assert message is not None
        assert message.payload.decode() == "lost"


def test_update_leds_with_monitor() -> None:
    unit = get_unit_name()
    exp = UNIVERSAL_EXPERIMENT

    with Monitor(unit=unit, experiment=exp):
        pause()
        pause()
        pause()
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/run/led_intensity",
            '{"options": {"A": 10, "B": 11}, "args": []}',
        )
        pause()
        pause()
        pause()
        pause()
        pause()
        with local_intermittent_storage("leds") as c:
            assert float(c["A"]) == 10.0
            assert float(c["B"]) == 11.0


def test_run_job_with_monitor() -> None:
    unit = get_unit_name()
    exp = UNIVERSAL_EXPERIMENT

    with collect_all_logs_of_level("DEBUG", unit, exp) as bucket:
        with Monitor(unit=unit, experiment=exp):
            pause()
            pause()
            publish(
                f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/run/example_plugin",
                b"",
            )
            pause()
            pause()
            pause()

        assert any("pio run example_plugin" in msg["message"] for msg in bucket)


def test_job_options_and_args_to_shell_command() -> None:
    m = Monitor
    assert (
        m._job_options_and_args_to_shell_command("stirring", [], {"target_rpm": 400})
        == "JOB_SOURCE=user nohup pio run stirring --target-rpm 400 >/dev/null 2>&1 &"
    )
    assert (
        m._job_options_and_args_to_shell_command("stirring", [], {"ignore_rpm": None})
        == "JOB_SOURCE=user nohup pio run stirring --ignore-rpm >/dev/null 2>&1 &"
    )
    assert (
        m._job_options_and_args_to_shell_command("stirring", [], {})
        == "JOB_SOURCE=user nohup pio run stirring >/dev/null 2>&1 &"
    )
    assert (
        m._job_options_and_args_to_shell_command("od_calibration", ["list"], {})
        == "JOB_SOURCE=user nohup pio run od_calibration list >/dev/null 2>&1 &"
    )
    assert (
        m._job_options_and_args_to_shell_command("stirring", [], {"job_source": "experiment_profile"})
        == "JOB_SOURCE=experiment_profile nohup pio run stirring >/dev/null 2>&1 &"
    )
