# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and perform LED actions. This is the core of the LED automation.

To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/led_control/led_automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"led_automation"`.
"""
import time
import json

import click
from contextlib import suppress
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.logging import create_logger


class LEDController(BackgroundJob):

    # this is automagically populated
    automations = {}

    published_settings = {"led_automation": {"datatype": "string", "settable": True}}

    def __init__(self, led_automation, unit: str, experiment: str, **kwargs):
        super(LEDController, self).__init__(
            job_name="led_control", unit=unit, experiment=experiment
        )

        self.led_automation = led_automation
        self.led_automation_job = self.automations[self.led_automation](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def set_led_automation(self, new_led_automation_json: str):
        algo_init = json.loads(new_led_automation_json)

        try:
            self.led_automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the job is created, let's protect against that.
            time.sleep(1)
            self.set_led_automation(new_led_automation_json)

        try:
            self.led_automation_job = self.automations[algo_init["led_automation"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.led_automation = algo_init["led_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self):
        if self.led_automation_job.state != self.SLEEPING:
            self.led_automation_job.set_state(self.SLEEPING)

    def on_ready(self):
        with suppress(AttributeError):
            if self.led_automation_job.state != self.READY:
                self.led_automation_job.set_state(self.READY)

    def on_disconnect(self):
        with suppress(AttributeError):
            self.led_automation_job.set_state("disconnected")

        self.clear_mqtt_cache()


def run(automation: str, duration: float = None, skip_first_run=False, **kwargs):
    try:
        return LEDController(
            automation,
            unit=get_unit_name(),
            experiment=get_latest_experiment_name(),
            skip_first_run=skip_first_run,
            duration=duration,
            **kwargs,
        )

    except Exception as e:
        logger = create_logger("led_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


@click.command(
    name="led_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system: silent, etc.",
    show_default=True,
)
@click.option(
    "--duration", default=60, help="Time, in minutes, between every monitor check"
)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally algo will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.pass_context
def click_led_control(ctx, automation, duration, skip_first_run):
    """
    Start an LED automation
    """
    lc = run(
        automation=automation,
        duration=duration,
        skip_first_run=skip_first_run,
        **{ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )

    lc.block_until_disconnected()
