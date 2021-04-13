# -*- coding: utf-8 -*-
import time

from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.subjobs.temperature_automation import Silent, PIDStable
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause(n=1):
    # to avoid race conditions when updating state
    time.sleep(n * 0.5)


def test_temperature_controller_logs_temperature():
    controller = TemperatureController(
        temperature_automation="silent", unit=unit, experiment=experiment
    )
    msg = pubsub.subscribe(
        f"pioreactor/{unit}/{experiment}/{controller.job_name}/temperature"
    )
    assert float(msg.payload) > 0


def test_pid_stable_automation():
    algo = PIDStable(target_temperature=50, unit=unit, experiment=experiment)
    pause(2)
    pubsub.publish(f"pioreactor/{unit}/{experiment}/temperature_control/temperature", 55)
    pause(2)
    algo.run()
    pause()
    algo.set_state("disconnected")


def test_changing_temperature_algo_over_mqtt_solo():

    algo = TemperatureController("silent", duration=10, unit=unit, experiment=experiment)
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
