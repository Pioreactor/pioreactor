# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs import temperature_control
from pioreactor.automations.temperature import Silent, PIDStable, ConstantDutyCycle
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause(n=1):
    # to avoid race conditions when updating state
    time.sleep(n)


def test_pid_stable_automation():
    with temperature_control.TemperatureController(
        "pid_stable", target_temperature=50, unit=unit, experiment=experiment
    ) as algo:
        pause(2)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
            '{"temperature": 55, "timestamp": "2020-01-01"}',
        )
        pause(2)

        algo.temperature_automation_job.target_temperature == 55


def test_changing_temperature_algo_over_mqtt():
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as algo:
        assert algo.temperature_automation == "silent"
        assert isinstance(algo.temperature_automation_job, Silent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature_automation/set",
            '{"temperature_automation": "pid_stable", "target_temperature": 20}',
        )
        time.sleep(8)
        assert algo.temperature_automation == "pid_stable"
        assert isinstance(algo.temperature_automation_job, PIDStable)
        assert algo.temperature_automation_job.target_temperature == 20


def test_changing_temperature_algo_over_mqtt_and_then_update_params():
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        None,
        retain=True,
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as algo:
        assert algo.temperature_automation == "silent"
        assert isinstance(algo.temperature_automation_job, Silent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature_automation/set",
            '{"temperature_automation": "constant_duty_cycle", "duty_cycle": 25}',
        )
        time.sleep(8)
        assert algo.temperature_automation == "constant_duty_cycle"
        assert isinstance(algo.temperature_automation_job, ConstantDutyCycle)
        assert algo.temperature_automation_job.duty_cycle == 25

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_automation/duty_cycle/set", 30
        )
        pause()
        assert algo.temperature_automation_job.duty_cycle == 30


def test_heating_is_reduced_when_set_temp_is_exceeded():

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        t.tmp_driver.get_temperature = lambda *args: t.MAX_TEMP_TO_REDUCE_HEATING + 0.1

        t._update_heater(50)
        assert t.heater_duty_cycle == 50
        pause()
        t.read_external_temperature()
        pause()

        assert 0 < t.heater_duty_cycle < 50


def test_heating_stops_when_max_temp_is_exceeded():

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        # monkey path the driver
        t.tmp_driver.get_temperature = lambda *args: t.MAX_TEMP_TO_DISABLE_HEATING + 0.1

        t._update_heater(50)
        assert t.heater_duty_cycle == 50
        pause()
        t.read_external_temperature()
        pause()

        assert t.heater_duty_cycle == 0


def test_child_cant_update_heater_when_locked():

    t = temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment, eval_and_publish_immediately=False
    )
    assert t.temperature_automation_job.update_heater(50)

    with t.pwm.lock_temporarily():
        assert not t.temperature_automation_job.update_heater(50)
        assert not t.update_heater(50)

    assert t.temperature_automation_job.update_heater(50)
    t.set_state(t.DISCONNECTED)


def test_constant_duty_cycle_init():
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


def test_setting_pid_control_after_startup_will_start_some_heating():
    # this test tries to replicate what a user does in the UI

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ) as t:
        # change to PID stable
        assert t.heater_duty_cycle == 0
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature_automation/set",
            '{"temperature_automation": "pid_stable", "target_temperature": 35}',
        )

        pause(3)
        assert t.heater_duty_cycle > 0


def test_duty_cycle_is_published_and_not_settable():

    dc_msgs = []

    def collect(msg):
        dc_msgs.append(msg.payload)

    pubsub.subscribe_and_callback(
        collect,
        f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/temperature_control/heater_duty_cycle",
    )

    with temperature_control.TemperatureController(
        "silent", unit=unit, experiment=experiment
    ):
        # change to PID stable

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/temperature_control/temperature_automation/set",
            '{"temperature_automation": "pid_stable", "target_temperature": 35}',
        )

        pause(3)

        # should produce an "Unable to set heater_duty_cycle"
        pubsub.publish(
            f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/temperature_control/heater_duty_cycle/set",
            10,
        )

        pause(1)

    assert len(dc_msgs) > 0
