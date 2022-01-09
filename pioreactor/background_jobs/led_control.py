# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and perform LED actions. This is the core of the LED automation.

To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/led_control/automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"automation_name"`.
"""
import time
import json
from contextlib import suppress

import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.logging import create_logger
from pioreactor.background_jobs.utils import AutomationDict


class LEDController(BackgroundJob):

    # this is automagically populated
    automations = {}  # type: ignore

    published_settings = {
        "automation": {"datatype": "json", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
    }

    def __init__(
        self, automation_name: str, unit: str, experiment: str, **kwargs
    ) -> None:
        super(LEDController, self).__init__(
            job_name="led_control", unit=unit, experiment=experiment
        )

        self.automation = AutomationDict(automation_name=automation_name, **kwargs)

        try:
            automation_class = self.automations[self.automation["automation_name"]]
        except KeyError:
            raise KeyError(
                f"Unable to find automation {self.automation['automation_name']}. Available automations are {list(self.automations.keys())}"
            )

        self.logger.info(f"Starting {self.automation}.")
        try:
            self.automation_job = automation_class(
                unit=self.unit, experiment=self.experiment, **kwargs
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.set_state(self.DISCONNECTED)
            raise e
        self.automation_name = self.automation["automation_name"]

    def set_automation(self, new_led_automation_json: str) -> None:
        algo_metadata = AutomationDict(json.loads(new_led_automation_json))

        try:
            self.automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the job is created, let's protect against that.
            time.sleep(1)
            self.set_automation(new_led_automation_json)

        try:
            klass = self.automations[algo_metadata["automation_name"]]
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = klass(
                unit=self.unit, experiment=self.experiment, **algo_metadata
            )
            self.automation = algo_metadata
            self.automation_name = self.automation["automation_name"]
        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata['automation_name']}. Available automations are {list(self.automations.keys())}",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata['automation_name']}. Available automations are {list(self.automations.keys())}"
            )

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self) -> None:
        if self.automation_job.state != self.SLEEPING:
            self.automation_job.set_state(self.SLEEPING)

    def on_ready(self) -> None:
        with suppress(AttributeError):
            if self.automation_job.state != self.READY:
                self.automation_job.set_state(self.READY)

    def on_disconnected(self) -> None:
        with suppress(AttributeError):
            self.automation_job.set_state(self.DISCONNECTED)


def start_led_control(
    automation_name: str, duration: float = None, skip_first_run=False, **kwargs
) -> LEDController:
    try:
        return LEDController(
            automation_name=automation_name,
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
    "--automation-name",
    default="silent",
    help="set the automation of the system: silent, etc.",
    show_default=True,
)
@click.option(
    "--duration", default=60.0, help="Time, in minutes, between every monitor check"
)
@click.option(
    "--skip-first-run",
    type=click.IntRange(min=0, max=1),
    help="Normally algo will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.pass_context
def click_led_control(ctx, automation_name, duration, skip_first_run):
    """
    Start an LED automation
    """
    lc = start_led_control(
        automation_name=automation_name,
        duration=duration,
        skip_first_run=bool(skip_first_run),
        **{
            ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1]
            for i in range(0, len(ctx.args), 2)
        },
    )

    lc.block_until_disconnected()
