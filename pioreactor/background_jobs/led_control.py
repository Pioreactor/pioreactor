# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and perform LED actions. This is the core of the LED automation.

To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/led_control/automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"automation_name"`.
"""
from __future__ import annotations

import time
from contextlib import suppress
from typing import Optional

import click

from pioreactor import exc
from pioreactor import hardware
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.structs import LEDAutomation
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


class LEDController(BackgroundJob):
    # this is automagically populated
    available_automations = {}  # type: ignore
    job_name = "led_control"
    published_settings = {
        "automation": {"datatype": "Automation", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
    }

    def __init__(self, unit: str, experiment: str, automation_name: str, **kwargs) -> None:
        super(LEDController, self).__init__(unit=unit, experiment=experiment)

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.clean_up()
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        try:
            automation_class = self.available_automations[automation_name]
        except KeyError:
            self.logger.error(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )
            self.clean_up()
            raise KeyError(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )

        self.automation = LEDAutomation(automation_name=automation_name, args=kwargs)
        self.logger.info(f"Starting {self.automation}.")
        try:
            self.automation_job = automation_class(
                unit=self.unit, experiment=self.experiment, **kwargs
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.clean_up()
            raise e
        self.automation_name = self.automation.automation_name

    def set_automation(self, algo_metadata: LEDAutomation) -> None:
        assert isinstance(algo_metadata, LEDAutomation)

        try:
            self.automation_job.clean_up()
        except AttributeError:
            # sometimes the user will change the job too fast before the job is created, let's protect against that.
            time.sleep(1)
            self.set_automation(algo_metadata)

        try:
            klass = self.available_automations[algo_metadata.automation_name]
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = klass(
                unit=self.unit, experiment=self.experiment, **algo_metadata.args
            )
            self.automation = algo_metadata
            self.automation_name = self.automation.automation_name
        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations.",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations."
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
            self.automation_job.clean_up()


def start_led_control(
    automation_name: str,
    duration: Optional[float] = None,
    skip_first_run=False,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> LEDController:
    return LEDController(
        unit=unit or get_unit_name(),
        experiment=experiment or get_latest_experiment_name(),
        automation_name=automation_name,
        skip_first_run=skip_first_run,
        duration=duration,
        **kwargs,
    )


@click.command(
    name="led_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    help="set the automation of the system: silent, etc.",
    show_default=True,
    required=True,
)
@click.option("--duration", default=60.0, help="Time, in minutes, between every monitor check")
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
    import os

    os.nice(1)

    lc = start_led_control(
        automation_name=automation_name,
        duration=duration,
        skip_first_run=bool(skip_first_run),
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )

    lc.block_until_disconnected()
