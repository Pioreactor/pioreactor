# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing automation.


To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/dosing_control/temperature_automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"temperature_automation"`.

"""
import json, signal

import click

from pioreactor.pubsub import QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.subjobs.temperature_automation import Silent, PIDStable
from pioreactor.logging import create_logger
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.utils import pio_jobs_running


class TemperatureController(BackgroundJob):

    automations = {"silent": Silent, "pid_stable": PIDStable}

    editable_settings = ["temperature_automation", "temperature"]

    def __init__(self, temperature_automation, unit=None, experiment=None, **kwargs):
        super(TemperatureController, self).__init__(
            job_name="temperature_control", unit=unit, experiment=experiment
        )
        self.temperature_automation = temperature_automation

        self.temperature_automation_job = self.automations[self.temperature_automation](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

        self.ema = ExponentialMovingAverage(0.1)

        try:
            from TMP1075 import TMP1075
        except (NotImplementedError, ModuleNotFoundError):
            self.logger.debug("TMP1075 not available; using MockTMP1075")
            from pioreactor.utils.mock import MockTMP1075 as TMP1075

        try:
            self.tmp_driver = TMP1075()
        except Exception as e:  # TODO: make specific
            self.logger.debug(e, exc_info=True)
            self.logger.error(
                "Is the Heating PCB attached to the RaspberryPi? Unable to find I²C for temperature driver."
            )

        self.publish_temperature_timer = RepeatedTimer(
            1 / config.getfloat("temperature_config.sampling", "samples_per_second"),
            self.read_and_publish_temperature,
            run_immediately=True,
        )
        self.publish_temperature_timer.start()

    def read_temperature(self):
        """
        Read the current temperature from our sensor, in Celsius
        """

        return self.tmp_driver.get_temperature()

    def read_and_publish_temperature(self):
        raw_temp = self.read_temperature()
        self.temperature = self.ema.update(raw_temp)
        self._check_if_exceeds_max_temp()
        self._check_for_sudden_temperature_decrease(raw_temp)

    def _check_for_sudden_temperature_decrease(self, raw_temp):
        # TODO: this needs to be tested in the field
        if (raw_temp < 0.75 * self.temperature) and (
            "dosing_control" in pio_jobs_running()
        ):
            self.logger.warning(
                "Noticed a sudden temperature change. This may be caused be a leakage. Suggestion is to check for liquid outside vial."
            )

    def _check_if_exceeds_max_temp(self):
        max_temp = 52.0
        if self.temperature > max_temp:
            self.logger.warning(
                f"Temperature of heating surface has exceeded {max_temp}℃. This is beyond our recommendations. Temperature automations will be halted. Take caution when touching the heating surface and wetware."
            )
            self.temperature_automation.set_state("disconnected")

    def set_temperature_automation(self, new_temperature_automation_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.temperature_automation_job.set_state("init")
        # self.temperature_automation_job.set_state("ready")
        # [ ] write tests
        # OR should just bail...
        try:
            algo_init = json.loads(new_temperature_automation_json)
            new_automation = algo_init["temperature_automation"]

            self.temperature_automation_job.set_state("disconnected")
            self.temperature_automation_job = self.automations[new_automation](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.temperature_automation = algo_init["temperature_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self):
        if self.temperature_automation_job.state != self.SLEEPING:
            self.temperature_automation_job.set_state(self.SLEEPING)

    def on_ready(self):
        try:
            if self.temperature_automation_job.state != self.READY:
                self.temperature_automation_job.set_state(self.READY)
        except AttributeError:
            # attribute error occurs on first init of _control
            pass

    def on_disconnect(self):
        try:
            self.temperature_automation_job.set_state(self.DISCONNECTED)
        except AttributeError:
            # if disconnect is called right after starting, temperature_automation_job isn't instantiated
            # time.sleep(1)
            # self.on_disconnect()
            # return
            pass
        finally:
            self.clear_mqtt_cache()

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        # TODO: this could move to the base class
        for attr in self.editable_settings:
            if attr in ["state", "temperature"]:
                continue
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.EXACTLY_ONCE,
            )


def run(automation=None, duration=None, skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["skip_first_run"] = skip_first_run

        controller = TemperatureController(automation, **kwargs)  # noqa: F841

        while True:
            signal.pause()

    except Exception as e:
        logger = create_logger("temperature_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


@click.command(name="temperature_control")
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system",
    show_default=True,
)
@click.option("--target-temperature", default=None, type=float)
@click.option(
    "--target-growth-rate", default=None, type=float, help="used in PIDMorbidostat only"
)
@click.option(
    "--duration",
    default=1 / config.getfloat("temperature_config.sampling", "samples_per_second"),
    help="in seconds",
)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
def click_temperature_control(
    automation, target_temperature, duration, target_growth_rate, skip_first_run
):
    """
    Start a temperature automation
    """
    controller = run(  # noqa: F841
        automation=automation,
        target_temperature=target_temperature,
        target_growth_rate=target_growth_rate,
        skip_first_run=skip_first_run,
        duration=duration,
    )
