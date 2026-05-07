# -*- coding: utf-8 -*-
import time
from typing import Any

import click
from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.automations.base import AutomationJob
from pioreactor.logging import create_logger


class LEDAutomationJob(AutomationJob):
    """
    This is the super class that LED automations inherit from. Subclasses choose
    how `execute` is scheduled, such as a periodic timer or a phase-boundary timer.
    """

    automation_name = "led_automation_base"  # is overwritten in subclasses
    job_name = "led_automation"

    published_settings: dict[str, pt.PublishableSetting] = {}

    latest_event: structs.AutomationEvent | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # this registers all subclasses of LEDAutomationJob
        if hasattr(cls, "automation_name") and getattr(cls, "automation_name") != "led_automation_base":
            available_led_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        **kwargs: Any,
    ) -> None:
        super(LEDAutomationJob, self).__init__(unit, experiment)

        self.edited_channels: set[pt.LedChannel] = set()

    def run(self, timeout: float = 60.0) -> structs.AutomationEvent | None:
        return self.run_once(timeout=timeout)

    def set_led_intensity(self, channel: pt.LedChannel, intensity: pt.LedIntensityValue) -> bool:
        """
        This first checks the lock on the LED channel, and will wait a few seconds for it to clear,
        and error out if it waits too long.

        Parameters
        ------------

        Channel:
            The LED channel to modify.
        Intensity: float
            A float between 0-100, inclusive.

        """
        attempts = 6
        for _ in range(attempts):
            success = led_intensity(
                {channel: intensity},
                unit=self.unit,
                experiment=self.experiment,
                pubsub_client=self.pub_client,
                source_of_event=f"{self.job_name}:{self.automation_name}",
            )

            if success:
                self.edited_channels.add(channel)
                return True

            time.sleep(0.5)

        self.logger.warning(f"{self.automation_name} was unable to update channel {channel}.")
        return False

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        super().on_disconnected()

        led_intensity(
            {channel: 0.0 for channel in self.edited_channels},
            unit=self.unit,
            experiment=self.experiment,
            pubsub_client=self.pub_client,
            source_of_event=f"{self.job_name}:{self.automation_name}",
        )


class LEDAutomationJobContrib(LEDAutomationJob):
    automation_name: str


def start_led_automation(
    automation_name: str,
    unit: str | None = None,
    experiment: str | None = None,
    **kwargs: Any,
) -> LEDAutomationJob:
    from pioreactor.automations import led  # noqa: F401

    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)
    try:
        klass = available_led_automations[automation_name]
    except KeyError:
        raise KeyError(
            f"Unable to find {automation_name}. Available automations are {list(available_led_automations.keys())}"
        )

    try:
        return klass(
            unit=unit,
            experiment=experiment,
            automation_name=automation_name,
            **kwargs,
        )

    except exc.JobPresentError:
        raise
    except Exception as e:
        logger = create_logger("led_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


available_led_automations: dict[str, type[LEDAutomationJob]] = {}


@click.command(
    name="led_automation",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    help="set the automation of the system: silent, etc.",
    show_default=True,
    required=True,
)
@click.pass_context
def click_led_automation(ctx: click.Context, automation_name: str) -> None:
    """
    Start an LED automation
    """

    with start_led_automation(
        automation_name=automation_name,
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    ) as la:
        la.block_until_disconnected()
