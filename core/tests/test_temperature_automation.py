# -*- coding: utf-8 -*-
import time

import pytest
from pioreactor import pubsub
from pioreactor import structs
from pioreactor.automations.temperature import OnlyRecordTemperature
from pioreactor.automations.temperature import Thermostat
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n)


@pytest.mark.slow
def test_thermostat_automation() -> None:
    experiment = "test_thermostat_automation"
    with Thermostat(target_temperature=50, unit=unit, experiment=experiment) as automation_job:
        pause(2)

        # 85 is too high - clamps to MAX_TARGET_TEMP
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/target_temperature/set",
            85,
        )
        pause(2)

        assert automation_job.target_temperature == automation_job.MAX_TARGET_TEMP

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/target_temperature/set",
            35,
        )
        pause(2)

        assert automation_job.target_temperature == 35


def test_heating_is_reduced_when_set_temp_is_exceeded() -> None:
    experiment = "test_heating_is_reduced_when_set_temp_is_exceeded"
    with OnlyRecordTemperature(unit=unit, experiment=experiment) as t:
        setattr(
            t.heating_pcb_tmp_driver,
            "get_temperature",
            lambda *args: t.MAX_TEMP_TO_REDUCE_HEATING + 0.1,
        )
        pause()
        t._update_heater(50)
        pause()
        assert t.heater_duty_cycle == 50
        pause()
        t.read_external_temperature()
        pause()

        assert 0 < t.heater_duty_cycle < 50


def test_static_values_can_be_edited() -> None:
    experiment = "test_heating_is_reduced_when_set_temp_is_exceeded"

    OnlyRecordTemperature.MAX_TEMP_TO_REDUCE_HEATING = 50  # type: ignore

    with OnlyRecordTemperature(unit=unit, experiment=experiment) as t:
        t.MAX_TEMP_TO_REDUCE_HEATING == 50


def test_thermostat_doesnt_fail_when_initial_target_is_less_than_initial_temperature() -> None:
    experiment = "test_thermostat_doesnt_fail_when_initial_target_is_less_than_initial_temperature"
    with Thermostat(unit=unit, experiment=experiment, target_temperature=20) as t:
        pause(3)
        assert t.state == "ready"
        assert t.heater_duty_cycle == 0


def test_heating_stops_when_max_temp_is_exceeded() -> None:
    experiment = "test_heating_stops_when_max_temp_is_exceeded"
    with Thermostat(
        unit=unit,
        experiment=experiment,
        target_temperature=25,
    ) as t:
        # monkey patch the driver
        setattr(
            t.heating_pcb_tmp_driver,
            "get_temperature",
            lambda *args: t.MAX_TEMP_TO_DISABLE_HEATING + 0.1,
        )
        pause()
        pause()
        t._update_heater(50)
        assert t.heater_duty_cycle == 50
        pause()
        pause()
        t.read_external_temperature()
        pause()
        pause()

        assert t.heater_duty_cycle == 0


def test_child_cant_update_heater_when_locked() -> None:
    experiment = "test_child_cant_update_heater_when_locked"
    with OnlyRecordTemperature(
        unit=unit,
        experiment=experiment,
    ) as t:
        assert t.update_heater(50)

        with t.pwm.lock_temporarily():
            assert not t.update_heater(50)
            assert not t.update_heater(50)

        assert t.update_heater(50)


def test_setting_pid_control_after_startup_will_start_some_heating() -> None:
    # this test tries to replicate what a user does in the UI
    experiment = "test_setting_pid_control_after_startup_will_start_some_heating"
    with Thermostat(unit=unit, experiment=experiment, target_temperature=35) as t:
        pause(3)
        assert t.state == "ready"
        assert t.heater_duty_cycle > 0


def test_setting_heat_is_turned_off_when_paused() -> None:
    # this test tries to replicate what a user does in the UI
    experiment = "test_setting_pid_control_after_startup_will_start_some_heating"
    with Thermostat(unit=unit, experiment=experiment, target_temperature=35) as t:
        pause(2)
        assert t.state == t.READY
        assert t.heater_duty_cycle > 0

        t.set_state(t.SLEEPING)

        assert t.state == t.SLEEPING
        assert t.heater_duty_cycle == 0


def test_duty_cycle_is_published_and_not_settable() -> None:
    experiment = "test_duty_cycle_is_published_and_not_settable"
    dc_msgs = []

    def collect(msg) -> None:
        dc_msgs.append(msg.payload)

    pubsub.subscribe_and_callback(
        collect,
        f"pioreactor/{unit}/{experiment}/temperature_automation/heater_duty_cycle",
    )

    with Thermostat(unit=unit, experiment=experiment, target_temperature=40):
        # should produce an "Unable to set heater_duty_cycle"
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/heater_duty_cycle/set",
            10,
        )

        pause(1)

    assert len(dc_msgs) > 0


def test_coprime() -> None:
    # seconds in read_external_temperature_timer should be coprime to seconds in publish_temperature_timer
    # so that they don't collide often
    from math import gcd as bltin_gcd

    def coprime2(a, b):
        return bltin_gcd(a, b) == 1

    experiment = "test_coprime"
    with Thermostat(unit=unit, experiment=experiment, target_temperature=30) as tc:
        assert coprime2(
            tc.read_external_temperature_timer.interval,
            tc.publish_temperature_timer.interval,
        )


def test_using_external_thermocouple() -> None:
    from pioreactor.automations.temperature.base import TemperatureAutomationJob
    from pioreactor.utils.timing import current_utc_datetime

    class MySuperSimpleAutomation(TemperatureAutomationJob):
        automation_name = "_test_my_super_simple_automation"

        def execute(self):
            self.latest_value_arrived = self.latest_temperature
            return

    experiment = "test_using_external_thermocouple"
    with MySuperSimpleAutomation(
        unit=unit,
        experiment=experiment,
        using_third_party_thermocouple=True,
    ) as tc:
        pause()
        pause()
        pause()
        assert tc.automation_name == "_test_my_super_simple_automation"

        # start publishing from our external temperature
        tc._set_latest_temperature(structs.Temperature(temperature=38, timestamp=current_utc_datetime()))

        assert tc.latest_value_arrived == 38
