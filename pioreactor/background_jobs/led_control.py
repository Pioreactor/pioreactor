# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and perform LED actions. This is the core of the LED automation.

To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/led_control/led_automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"led_automation"`.
"""
import signal

import json
import logging

import click

from pioreactor.pubsub import QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.subjobs.led_automation import Silent, FlashUV, TrackOD


class LEDController(BackgroundJob):

    automations = {"silent": Silent, "flash_uv": FlashUV, "track_od": TrackOD}

    editable_settings = ["led_automation"]

    def __init__(self, led_automation, unit=None, experiment=None, **kwargs):
        super(LEDController, self).__init__(
            job_name="led_control", unit=unit, experiment=experiment
        )
        self.led_automation = led_automation

        self.led_automation_job = self.automations[self.led_automation](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def set_led_automation(self, new_led_automation_json):
        try:
            algo_init = json.loads(new_led_automation_json)

            self.led_automation_job.set_state("disconnected")

            self.led_automation_job = self.automations[algo_init["led_automation"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.led_automation = algo_init["led_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_disconnect(self):
        try:
            self.led_automation_job.set_state("disconnected")
            self.clear_mqtt_cache()
        except AttributeError:
            # if disconnect is called right after starting, led_automation_job isn't instantiated
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

        controller = LEDController(automation, **kwargs)  # noqa: F841

        while True:
            signal.pause()

    except Exception as e:
        logging.getLogger("led_automation").debug(e, exc_info=True)
        logging.getLogger("led_automation").error(e)
        raise e


@click.command(name="led_control")
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system: silent, etc.",
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
    automation, target_od, target_growth_rate, duration, volume, sensor, skip_first_run
):
    """
    Start an LED automation
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
