# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing automation.


To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/dosing_control/dosing_automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"dosing_automation"`.

"""
import signal

import json
import logging

import click

from pioreactor.pubsub import QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob

from pioreactor.dosing_automations.morbidostat import Morbidostat
from pioreactor.dosing_automations.pid_morbidostat import PIDMorbidostat
from pioreactor.dosing_automations.pid_turbidostat import PIDTurbidostat
from pioreactor.dosing_automations.silent import Silent
from pioreactor.dosing_automations.turbidostat import Turbidostat
from pioreactor.dosing_automations.chemostat import Chemostat


class DosingController(BackgroundJob):

    automations = {
        "silent": Silent,
        "morbidostat": Morbidostat,
        "turbidostat": Turbidostat,
        "chemostat": Chemostat,
        "pid_turbidostat": PIDTurbidostat,
        "pid_morbidostat": PIDMorbidostat,
    }

    editable_settings = ["dosing_automation"]

    def __init__(self, dosing_automation, unit=None, experiment=None, **kwargs):
        super(DosingController, self).__init__(
            job_name="dosing_control", unit=unit, experiment=experiment
        )
        self.dosing_automation = dosing_automation

        self.dosing_automation_job = self.automations[self.dosing_automation](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def set_dosing_automation(self, new_dosing_automation_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.dosing_automation_job.set_state("init")
        # self.dosing_automation_job.set_state("ready")
        # [ ] write tests
        # OR should just bail...
        try:
            algo_init = json.loads(new_dosing_automation_json)

            self.dosing_automation_job.set_state("disconnected")

            self.dosing_automation_job = self.automations[algo_init["dosing_automation"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.dosing_automation = algo_init["dosing_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self):
        if self.dosing_automation_job.state != self.SLEEPING:
            self.dosing_automation_job.set_state(self.SLEEPING)

    def on_ready(self):
        try:
            if self.dosing_automation_job.state != self.READY:
                self.dosing_automation_job.set_state(self.READY)
        except AttributeError:
            # attribute error occurs on first init of _control
            pass

    def on_disconnect(self):
        try:
            self.dosing_automation_job.set_state(self.DISCONNECTED)
            self.clear_mqtt_cache()
        except AttributeError:
            # if disconnect is called right after starting, dosing_automation_job isn't instantiated
            # time.sleep(1)
            # self.on_disconnect()
            # return
            pass

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        # TODO: this could move to the base class
        for attr in self.editable_settings:
            if attr == "state":
                continue
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.EXACTLY_ONCE,
            )


def run(automation=None, duration=None, sensor="135/0", skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["sensor"] = sensor
        kwargs["skip_first_run"] = skip_first_run

        controller = DosingController(automation, **kwargs)  # noqa: F841

        while True:
            signal.pause()

    except Exception as e:
        logging.getLogger("dosing_automation").debug(f"{str(e)}", exc_info=True)
        logging.getLogger("dosing_automation").error(f"{str(e)}")
        raise e


@click.command(name="dosing_control")
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system: turbidostat, morbidostat, silent, etc.",
    show_default=True,
)
@click.option("--target-od", default=None, type=float)
@click.option(
    "--target-growth-rate", default=None, type=float, help="used in PIDMorbidostat only"
)
@click.option(
    "--duration", default=60, help="Time, in minutes, between every monitor check"
)
@click.option("--volume", default=None, help="the volume to exchange, mL", type=float)
@click.option("--sensor", default="+", show_default=True)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
def click_dosing_control(
    automation, target_od, target_growth_rate, duration, volume, sensor, skip_first_run
):
    """
    Start a dosing automation
    """
    controller = run(  # noqa: F841
        automation=automation,
        target_od=target_od,
        target_growth_rate=target_growth_rate,
        duration=duration,
        volume=volume,
        skip_first_run=skip_first_run,
        sensor=sensor,
    )
