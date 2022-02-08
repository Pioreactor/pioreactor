# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time

from pioreactor import pubsub
from pioreactor.automations.temperature import ConstantDutyCycle
from pioreactor.automations.temperature import Silent
from pioreactor.automations.temperature import Stable
from pioreactor.background_jobs import temperature_control
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n)


def test_stable_automation() -> None:
    experiment = "test_stable_automation"
    with temperature_control.TemperatureController(
        "stable", target_temperature=50, unit=unit, experiment=experiment
    ) as algo:
        pause(2)

        # 55 is too high - clamps to 50
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/target_temperature/set",
            55,
        )
        pause(2)

        assert algo.automation_job.target_temperature == 50

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/target_temperature/set",
            35,
        )
        pause(2)

        assert algo.automation_job.target_temperature == 35


def test_changing_temperature_algo_over_mqtt() -> None:
    experiment = "test_changing_temperature_algo_over_mqtt"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as algo:
        assert algo.automation_name == "silent"
        assert isinstance(algo.automation_job, Silent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            '{"automation_name": "stable", "target_temperature": 20}',
        )
        time.sleep(8)
        assert algo.automation_name == "stable"
        assert isinstance(algo.automation_job, Stable)
        assert algo.automation_job.target_temperature == 20


def test_changing_temperature_algo_over_mqtt_and_then_update_params() -> None:
    experiment = "test_changing_temperature_algo_over_mqtt_and_then_update_params"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as algo:
        assert algo.automation_name == "silent"
        assert isinstance(algo.automation_job, Silent)
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            '{"automation_name": "constant_duty_cycle", "duty_cycle": 25}',
        )
        time.sleep(15)
        assert algo.automation_name == "constant_duty_cycle"
        assert isinstance(algo.automation_job, ConstantDutyCycle)
        assert algo.automation_job.duty_cycle == 25

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/duty_cycle/set", 30
        )
        pause()
        assert algo.automation_job.duty_cycle == 30


def test_heating_is_reduced_when_set_temp_is_exceeded() -> None:
    experiment = "test_heating_is_reduced_when_set_temp_is_exceeded"
    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        t.tmp_driver.get_temperature = lambda *args: t.MAX_TEMP_TO_REDUCE_HEATING + 0.1
        pause()
        t._update_heater(50)
        pause()
        assert t.heater_duty_cycle == 50
        pause()
        t.read_external_temperature_and_check_temp()
        pause()

        assert 0 < t.heater_duty_cycle < 50


def test_stable_doesnt_fail_when_initial_target_is_less_than_initial_temperature() -> None:
    experiment = (
        "test_stable_doesnt_fail_when_initial_target_is_less_than_initial_temperature"
    )
    with temperature_control.TemperatureController(
        "stable", unit=unit, experiment=experiment, target_temperature=20
    ) as t:

        pause(3)
        assert t.automation_job.state == "ready"
        assert t.heater_duty_cycle == 0


def test_heating_stops_when_max_temp_is_exceeded() -> None:
    experiment = "test_heating_stops_when_max_temp_is_exceeded"
    with temperature_control.TemperatureController(
        "stable",
        unit=unit,
        experiment=experiment,
        target_temperature=25,
    ) as t:
        # monkey patch the driver
        t.tmp_driver.get_temperature = lambda *args: t.MAX_TEMP_TO_DISABLE_HEATING + 0.1
        pause()
        pause()
        t._update_heater(50)
        assert t.heater_duty_cycle == 50
        pause()
        pause()
        t.read_external_temperature_and_check_temp()
        pause()
        pause()

        assert t.heater_duty_cycle == 0
        assert t.automation_name == "silent"


def test_child_cant_update_heater_when_locked() -> None:
    experiment = "test_child_cant_update_heater_when_locked"
    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment, eval_and_publish_immediately=False
    ) as t:
        assert t.automation_job.update_heater(50)

        with t.pwm.lock_temporarily():
            assert not t.automation_job.update_heater(50)
            assert not t.update_heater(50)

        assert t.automation_job.update_heater(50)


def test_constant_duty_cycle_init() -> None:
    experiment = "test_constant_duty_cycle_init"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    dc = 50
    with temperature_control.TemperatureController(
        "constant_duty_cycle", unit=unit, experiment=experiment, duty_cycle=dc
    ) as algo:
        pause()
        assert algo.heater_duty_cycle == 50


def test_setting_pid_control_after_startup_will_start_some_heating() -> None:
    # this test tries to replicate what a user does in the UI
    experiment = "test_setting_pid_control_after_startup_will_start_some_heating"
    with temperature_control.TemperatureController(
        "stable", unit=unit, experiment=experiment, target_temperature=35
    ) as t:

        pause(3)
        assert t.automation_job.state == "ready"
        assert t.heater_duty_cycle > 0


def test_duty_cycle_is_published_and_not_settable() -> None:
    experiment = "test_duty_cycle_is_published_and_not_settable"
    dc_msgs = []

    def collect(msg) -> None:
        dc_msgs.append(msg.payload)

    pubsub.subscribe_and_callback(
        collect,
        f"pioreactor/{unit}/{experiment}/temperature_control/heater_duty_cycle",
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ):
        # change to PID stable

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            '{"automation_name": "stable", "target_temperature": 35}',
        )

        pause(3)

        # should produce an "Unable to set heater_duty_cycle"
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/heater_duty_cycle/set",
            10,
        )

        pause(1)

    assert len(dc_msgs) > 0


def test_temperature_approximation1() -> None:
    experiment = "test_temperature_approximation1"
    features = {
        "previous_heater_dc": 17,
        "time_series_of_temp": [
            37.8125,
            36.625,
            35.6875,
            35.0,
            34.5,
            34.0625,
            33.6875,
            33.4375,
            33.1875,
            33.0,
            32.875,
            32.6875,
            32.5625,
            32.4375,
            32.375,
            32.25,
            32.1875,
        ],
    }

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert 32.0 <= t.approximate_temperature(features) <= 33.4


def test_temperature_approximation2() -> None:
    experiment = "test_temperature_approximation2"
    features = {
        "previous_heater_dc": 17,
        "time_series_of_temp": [
            44.8125,
            43.8125,
            43.0,
            42.25,
            41.5625,
            40.875,
            40.3125,
            39.75,
            39.1875,
            38.6875,
            38.25,
            37.8125,
            37.375,
            37.0,
            36.625,
            36.25,
            35.9375,
        ],
    }

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert 38 <= t.approximate_temperature(features) <= 39


def test_temperature_approximation3() -> None:
    experiment = "test_temperature_approximation3"
    features = {
        "previous_heater_dc": 17,
        "time_series_of_temp": [
            49.875,
            47.5,
            45.8125,
            44.375,
            43.1875,
            42.0625,
            41.125,
            40.3125,
            39.5625,
            38.875,
            38.1875,
            37.625,
            37.125,
            36.625,
            36.1875,
            35.8125,
            35.4375,
        ],
    }

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert 39 <= t.approximate_temperature(features) <= 40


def test_temperature_approximation_if_constant() -> None:
    experiment = "test_temperature_approximation_if_constant"
    features = {"previous_heater_dc": 17, "time_series_of_temp": 30 * [32.0]}

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert abs(32.0 - t.approximate_temperature(features)) < 0.01


def test_temperature_approximation_even_if_very_tiny_heat_source() -> None:
    import numpy as np

    experiment = "test_temperature_approximation_even_if_very_tiny_heat_source"
    features = {
        "previous_heater_dc": 14.5,
        "time_series_of_temp": list(
            22
            + 10 * np.exp(-0.008 * np.arange(0, 17))
            + 0.5 * np.exp(-0.28 * np.arange(0, 17))
        ),
    }

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert (32 * np.exp(-0.008 * 17)) < t.approximate_temperature(features) < 32


def test_temperature_approximation_even_if_very_large_heat_source() -> None:
    import numpy as np

    experiment = "test_temperature_approximation_even_if_very_large_heat_source"
    features = {
        "previous_heater_dc": 14.5,
        "time_series_of_temp": list(
            22
            + 3 * np.exp(-0.008 * np.arange(0, 17))
            + 20 * np.exp(-0.28 * np.arange(0, 17))
        ),
    }

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert (24 * np.exp(-0.008 * 17)) < t.approximate_temperature(features) < 25


def test_temperature_approximation_if_dc_is_nil() -> None:
    experiment = "test_temperature_approximation_if_dc_is_nil"
    features = {"previous_heater_dc": 0, "time_series_of_temp": [37.8125, 32.1875]}

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        assert t.approximate_temperature(features) == 32.1875


def test_temperature_control_and_stables_relationship():
    experiment = "test_temperature_control_and_stables_relationship"
    with temperature_control.TemperatureController(
        "stable", unit=unit, experiment=experiment, target_temperature=30
    ) as tc:
        tc.publish_temperature_timer.pause()  # pause this for now. we will manually run evaluate_and_publish_temperature

        pause()
        pause()
        assert tc.heater_duty_cycle > 0
        initial_dc = tc.heater_duty_cycle

        stable_automation = tc.automation_job
        # suppose we want to update target_temperature...
        stable_automation.set_target_temperature(35)
        pause()

        # should have changed the dc immediately.
        assert tc.heater_duty_cycle != initial_dc
        assert tc.heater_duty_cycle > 0
        pause()

        # run evaluate_and_publish_temperature, this locks the PWM from anyone updating it directly.
        thread = threading.Thread(target=tc.evaluate_and_publish_temperature, daemon=True)
        thread.start()
        pause()

        assert tc.heater_duty_cycle == 0
        pause()

        # suppose we want to update target_temperature...
        stable_automation.set_target_temperature(40)
        pause()

        # should still be 0!
        assert tc.heater_duty_cycle == 0
        pause()

        thread.join()  # this takes a while


def test_coprime():
    # seconds in read_external_temperature_timer should be coprime to seconds in publish_temperature_timer
    # so that they don't collide often
    from math import gcd as bltin_gcd

    def coprime2(a, b):
        return bltin_gcd(a, b) == 1

    experiment = "test_coprime"
    with temperature_control.TemperatureController(
        "stable", unit=unit, experiment=experiment, target_temperature=30
    ) as tc:
        assert coprime2(
            tc.read_external_temperature_timer.interval,
            tc.publish_temperature_timer.interval,
        )
