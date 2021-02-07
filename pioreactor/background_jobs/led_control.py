# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and perform LED actions. This is the core of the LED algorithm.

To change the algorithm over MQTT,

topic: `pioreactor/<unit>/<experiment>/led_control/led_algorithm/set`
message: a json object with required keyword argument. Specify the new algorithm with name `"led_algorithm"`.
"""
import signal

import json
import logging

import click

from pioreactor.pubsub import QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.subjobs.led_algorithm import Silent, FlashUV, TrackOD


class LEDController(BackgroundJob):

    algorithms = {"silent": Silent, "flash_uv": FlashUV, "track_od": TrackOD}

    editable_settings = ["led_algorithm"]

    def __init__(self, led_algorithm, unit=None, experiment=None, **kwargs):
        super(LEDController, self).__init__(
            job_name="led_control", unit=unit, experiment=experiment
        )
        self.led_algorithm = led_algorithm

        self.led_algorithm_job = self.algorithms[self.led_algorithm](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def set_led_algorithm(self, new_led_algorithm_json):
        try:
            algo_init = json.loads(new_led_algorithm_json)

            self.led_algorithm_job.set_state("disconnected")

            self.led_algorithm_job = self.algorithms[algo_init["led_algorithm"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.led_algorithm = algo_init["led_algorithm"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_disconnect(self):
        try:
            self.led_algorithm_job.set_state("disconnected")
            self.clear_mqtt_cache()
        except AttributeError:
            # if disconnect is called right after starting, led_algorithm_job isn't instantiated
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


def run(algorithm=None, duration=None, sensor="135/0", skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["sensor"] = sensor
        kwargs["skip_first_run"] = skip_first_run

        controller = LEDController(algorithm, **kwargs)  # noqa: F841

        while True:
            signal.pause()

    except Exception as e:
        logging.getLogger("led_algorithm").debug(e, exc_info=True)
        logging.getLogger("led_algorithm").error(e)
        raise e


@click.command(name="led_control")
@click.option(
    "--algorithm",
    default="silent",
    help="set the algorithm of the system: silent, etc.",
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
@click.option("--sensor", default="135/0", show_default=True)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally algo will run immediately. Set this flag to wait <duration>min before executing.",
)
def click_led_control(
    algorithm, target_od, target_growth_rate, duration, volume, sensor, skip_first_run
):
    """
    Start an LED algorithm
    """
    controller = run(  # noqa: F841
        algorithm=algorithm,
        target_od=target_od,
        target_growth_rate=target_growth_rate,
        duration=duration,
        volume=volume,
        skip_first_run=skip_first_run,
        sensor=sensor,
    )
