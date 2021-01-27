# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing algorithm.


To change the algorithm over MQTT,

topic: `pioreactor/<unit>/<experiment>/dosing_control/dosing_algorithm/set`
message: a json object with required keyword argument. Specify the new algorithm with name `"dosing_algorithm"`.

"""
import signal

import json
import logging

import click

from pioreactor.pubsub import QOS
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob

from pioreactor.dosing_algorithms.morbidostat import Morbidostat
from pioreactor.dosing_algorithms.pid_morbidostat import PIDMorbidostat
from pioreactor.dosing_algorithms.pid_turbidostat import PIDTurbidostat
from pioreactor.dosing_algorithms.silent import Silent
from pioreactor.dosing_algorithms.turbidostat import Turbidostat
from pioreactor.dosing_algorithms.chemostat import Chemostat


class DosingController(BackgroundJob):

    algorithms = {
        "silent": Silent,
        "morbidostat": Morbidostat,
        "turbidostat": Turbidostat,
        "chemostat": Chemostat,
        "pid_turbidostat": PIDTurbidostat,
        "pid_morbidostat": PIDMorbidostat,
    }

    editable_settings = ["dosing_algorithm"]

    def __init__(self, dosing_algorithm, unit=None, experiment=None, **kwargs):
        super(DosingController, self).__init__(
            job_name="dosing_control", unit=unit, experiment=experiment
        )
        self.check_for_existing_dosing_algorithm_process()

        self.dosing_algorithm = dosing_algorithm

        self.dosing_algorithm_job = self.algorithms[self.dosing_algorithm](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def check_for_existing_dosing_algorithm_process(self):
        # this is needed because the running process != the job name. This is techdebt.
        if sum([p == "dosing_algorithm" for p in pio_jobs_running()]) > 1:
            self.logger.error("dosing_algorithm is already running. Aborting.")
            raise ValueError("dosing_algorithm is already running. Aborting.")

    def set_dosing_algorithm(self, new_dosing_algorithm_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.dosing_algorithm_job.set_state("init")
        # self.dosing_algorithm_job.set_state("ready")
        # [ ] write tests
        # OR should just bail...
        try:
            algo_init = json.loads(new_dosing_algorithm_json)

            self.dosing_algorithm_job.set_state("disconnected")

            self.dosing_algorithm_job = self.algorithms[algo_init["dosing_algorithm"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.dosing_algorithm = algo_init["dosing_algorithm"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_disconnect(self):
        try:
            self.dosing_algorithm_job.set_state("disconnected")
            self.clear_mqtt_cache()
        except AttributeError:
            # if disconnect is called right after starting, dosing_algorithm_job isn't instantiated
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


def run(mode=None, duration=None, sensor="135/A", skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["sensor"] = sensor
        kwargs["skip_first_run"] = skip_first_run

        controller = DosingController(mode, **kwargs)  # noqa: F841

        while True:
            signal.pause()

    except Exception as e:
        logging.getLogger("dosing_algorithm").debug(f"{str(e)}", exc_info=True)
        logging.getLogger("dosing_algorithm").error(f"{str(e)}")
        raise e


@click.command(name="dosing_control")
@click.option(
    "--mode",
    default="silent",
    help="set the mode of the system: turbidostat, morbidostat, silent, etc.",
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
@click.option("--sensor", default="135/A", show_default=True)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
def click_dosing_control(
    mode, target_od, target_growth_rate, duration, volume, sensor, skip_first_run
):
    """
    Start a dosing algorithm
    """
    controller = run(  # noqa: F841
        mode=mode,
        target_od=target_od,
        target_growth_rate=target_growth_rate,
        duration=duration,
        volume=volume,
        skip_first_run=skip_first_run,
        sensor=sensor,
    )
