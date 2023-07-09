# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time

from msgspec.json import encode

from pioreactor import pubsub
from pioreactor import structs
from pioreactor.automations.temperature import ConstantDutyCycle
from pioreactor.automations.temperature import OnlyRecordTemperature
from pioreactor.automations.temperature import Thermostat
from pioreactor.background_jobs import temperature_control
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n)


def test_thermostat_automation() -> None:
    experiment = "test_thermostat_automation"
    with temperature_control.TemperatureController(
        "thermostat", target_temperature=50, unit=unit, experiment=experiment
    ) as algo:
        pause(2)

        # 55 is too high - clamps to MAX_TARGET_TEMP
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/target_temperature/set",
            55,
        )
        pause(2)

        assert algo.automation_job.target_temperature == algo.automation_job.MAX_TARGET_TEMP

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
        "only_record_temperature", unit=unit, experiment=experiment
    ) as tc:
        assert tc.automation_name == "only_record_temperature"
        assert isinstance(tc.automation_job, OnlyRecordTemperature)
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            encode(
                structs.TemperatureAutomation(
                    automation_name="thermostat", args={"target_temperature": 36}
                )
            ),
        )
        time.sleep(8)
        assert tc.automation_name == "thermostat"
        assert isinstance(tc.automation_job, Thermostat)
        assert tc.automation_job.target_temperature == 36
        assert tc.automation_job.latest_temperature is not None
        assert tc.heater_duty_cycle > 0


def test_changing_temperature_algo_over_mqtt_and_then_update_params() -> None:
    experiment = "test_changing_temperature_algo_over_mqtt_and_then_update_params"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    with temperature_control.TemperatureController(
        "only_record_temperature", unit=unit, experiment=experiment
    ) as algo:
        assert algo.automation_name == "only_record_temperature"
        assert isinstance(algo.automation_job, OnlyRecordTemperature)
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            encode(
                structs.TemperatureAutomation(
                    automation_name="constant_duty_cycle", args={"duty_cycle": 25}
                )
            ),
        )
        time.sleep(15)
        assert algo.automation_name == "constant_duty_cycle"
        assert isinstance(algo.automation_job, ConstantDutyCycle)
        assert algo.automation_job.duty_cycle == 25

        pubsub.publish(f"pioreactor/{unit}/{experiment}/temperature_automation/duty_cycle/set", 30)
        pause()
        assert algo.automation_job.duty_cycle == 30


def test_heating_is_reduced_when_set_temp_is_exceeded() -> None:
    experiment = "test_heating_is_reduced_when_set_temp_is_exceeded"
    with temperature_control.TemperatureController(
        "only_record_temperature", unit=unit, experiment=experiment
    ) as t:
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


def test_thermostat_doesnt_fail_when_initial_target_is_less_than_initial_temperature() -> None:
    experiment = "test_thermostat_doesnt_fail_when_initial_target_is_less_than_initial_temperature"
    with temperature_control.TemperatureController(
        "thermostat", unit=unit, experiment=experiment, target_temperature=20
    ) as t:
        pause(3)
        assert t.automation_job.state == "ready"
        assert t.heater_duty_cycle == 0


def test_heating_stops_when_max_temp_is_exceeded() -> None:
    experiment = "test_heating_stops_when_max_temp_is_exceeded"
    with temperature_control.TemperatureController(
        "thermostat",
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
        assert t.automation_name == "only_record_temperature"


def test_child_cant_update_heater_when_locked() -> None:
    experiment = "test_child_cant_update_heater_when_locked"
    with temperature_control.TemperatureController(
        "only_record_temperature",
        unit=unit,
        experiment=experiment,
        eval_and_publish_immediately=False,
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
        "thermostat", unit=unit, experiment=experiment, target_temperature=35
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
        "only_record_temperature", unit=unit, experiment=experiment
    ):
        # change to PID thermostat

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            encode(
                structs.TemperatureAutomation(
                    automation_name="thermostat", args={"target_temperature": 35}
                )
            ),
        )

        pause(3)

        # should produce an "Unable to set heater_duty_cycle"
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/heater_duty_cycle/set",
            10,
        )

        pause(1)

    assert len(dc_msgs) > 0


def test_temperature_control_and_thermostats_relationship() -> None:
    experiment = "test_temperature_control_and_thermostats_relationship"
    with temperature_control.TemperatureController(
        "thermostat", unit=unit, experiment=experiment, target_temperature=30
    ) as tc:
        tc.publish_temperature_timer.pause()  # pause this for now. we will manually run evaluate_and_publish_temperature
        pause()
        pause()
        thermostat_automation = tc.automation_job
        initial_dc = tc.heater_duty_cycle

        assert initial_dc > 0

        # suppose we want to update target_temperature...
        thermostat_automation.set_target_temperature(35)
        pause()

        # should have changed the dc immediately.
        assert tc.heater_duty_cycle != initial_dc
        assert tc.heater_duty_cycle > 0
        pause()

        # run evaluate_and_publish_temperature, this locks the PWM from anyone updating it directly.
        thread = threading.Thread(target=tc.infer_temperature, daemon=True)
        thread.start()
        pause()

        assert tc.heater_duty_cycle == 0
        pause()

        # suppose we want to update target_temperature...
        thermostat_automation.set_target_temperature(40)
        pause()

        # should still be 0!
        assert tc.heater_duty_cycle == 0
        pause()

        thread.join()  # this takes a while


def test_coprime() -> None:
    # seconds in read_external_temperature_timer should be coprime to seconds in publish_temperature_timer
    # so that they don't collide often
    from math import gcd as bltin_gcd

    def coprime2(a, b):
        return bltin_gcd(a, b) == 1

    experiment = "test_coprime"
    with temperature_control.TemperatureController(
        "thermostat", unit=unit, experiment=experiment, target_temperature=30
    ) as tc:
        assert coprime2(
            tc.read_external_temperature_timer.interval,
            tc.publish_temperature_timer.interval,
        )


def test_using_external_thermocouple() -> None:
    from pioreactor.automations.temperature.base import TemperatureAutomationJob
    from pioreactor.utils.timing import current_utc_datetime

    class MySuperSimpleAutomation(TemperatureAutomationJob):
        automation_name = "my_super_simple_automation"

        def execute(self):
            self.latest_value_arrived = self.latest_temperature
            return

    experiment = "test_using_external_thermocouple"
    with temperature_control.TemperatureController(
        "only_record_temperature",
        unit=unit,
        experiment=experiment,
        using_third_party_thermocouple=True,
    ) as tc:
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            encode(structs.TemperatureAutomation(automation_name="my_super_simple_automation")),
        )
        pause()
        pause()
        pause()
        pause()
        pause()
        assert tc.automation_name == "my_super_simple_automation"

        # start publishing from our external temperature
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
            encode(structs.Temperature(temperature=38, timestamp=current_utc_datetime())),
        )
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
            encode(structs.Temperature(temperature=39, timestamp=current_utc_datetime())),
        )
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
            encode(structs.Temperature(temperature=40, timestamp=current_utc_datetime())),
        )
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
            encode(structs.Temperature(temperature=41, timestamp=current_utc_datetime())),
        )
        pause()

        assert tc.automation_job.latest_value_arrived == 41


def test_that_if_a_user_tries_to_change_thermostat_X_to_thermostat_Y_we_just_change_the_attr_instead_of_the_entire_automation():
    experiment = "test_that_if_a_user_tries_to_change_thermostat_X_to_thermostat_Y_we_just_change_the_attr_instead_of_the_entire_automation"

    with temperature_control.TemperatureController(
        "thermostat", target_temperature=30, unit=unit, experiment=experiment
    ) as tc:
        assert tc.automation_name == "thermostat"
        assert isinstance(tc.automation_job, Thermostat)

        tc.automation_job.test_attr = True

        pause()

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/automation/set",
            encode(
                structs.TemperatureAutomation(
                    automation_name="thermostat", args={"target_temperature": 36}
                )
            ),
        )

        pause(8)
        assert tc.automation_name == "thermostat"
        assert isinstance(tc.automation_job, Thermostat)
        assert tc.automation_job.target_temperature == 36

        assert hasattr(tc.automation_job, "test_attr")
        assert tc.automation_job.test_attr
