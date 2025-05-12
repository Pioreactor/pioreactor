# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from threading import Thread
from typing import Optional

import click

from pioreactor import exc
from pioreactor import types as pt
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.automations import events
from pioreactor.automations.base import AutomationJob
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.utils import whoami
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer


def brief_pause() -> float:
    d = 5.0
    time.sleep(d)
    return d


class LEDAutomationJob(AutomationJob):
    """
    This is the super class that LED automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program), and call the `execute` function
    which is what subclasses define.
    """

    automation_name = "led_automation_base"  # is overwritten in subclasses
    job_name = "led_automation"

    published_settings: dict[str, pt.PublishableSetting] = {}

    _latest_run_at: Optional[datetime] = None

    latest_event: Optional[events.AutomationEvent] = None
    run_thread: RepeatedTimer | Thread

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # this registers all subclasses of LEDAutomationJob
        if hasattr(cls, "automation_name") and getattr(cls, "automation_name") != "led_automation_base":
            available_led_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        duration: float,
        skip_first_run: bool = False,
        **kwargs,
    ) -> None:
        super(LEDAutomationJob, self).__init__(unit, experiment)

        self.add_to_published_settings(
            "duration",
            {
                "datatype": "float",
                "settable": True,
                "unit": "min",
            },
        )

        self.skip_first_run = skip_first_run
        self.edited_channels: set[pt.LedChannel] = set()

        self.set_duration(duration)

    def set_duration(self, duration: float) -> None:
        self.duration = float(duration)
        if self._latest_run_at is not None:
            # what's the correct logic when changing from duration N and duration M?
            # - N=20, and it's been 5m since the last run (or initialization). I change to M=30, I should wait M-5 minutes.
            # - N=60, and it's been 50m since last run. I change to M=30, I should run immediately.
            run_after = max(
                0,
                (self.duration * 60) - (current_utc_datetime() - self._latest_run_at).seconds,
            )
        else:
            # there is a race condition here: self.run() will run immediately (see run_immediately), but the state of the job is not READY, since
            # set_duration is run in the __init__ (hence the job is INIT). So we wait 2 seconds for the __init__ to finish, and then run.
            # Later: in fact, we actually want this to run after an OD reading cycle so we have internal data, so it should wait a cycle of that.
            run_after = min(
                1.0 / config.getfloat("od_reading.config", "samples_per_second"), 10
            )  # max so users aren't waiting forever to see lights come on...
        self.run_thread = RepeatedTimer(
            self.duration * 60,  # RepeatedTimer uses seconds
            self.run,
            job_name=self.job_name,
            run_immediately=(not self.skip_first_run) or (self._latest_run_at is not None),
            run_after=run_after,
            logger=self.logger,
        ).start()

    def run(self, timeout: float = 60.0) -> Optional[events.AutomationEvent]:
        """
        Parameters
        -----------
        timeout: float
            if the job is not in a READY state after timeout seconds, skip calling `execute` this period.
            Default 60s.

        """
        event: Optional[events.AutomationEvent]
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return None

        elif self.state != self.READY:
            sleep_for = brief_pause()
            # wait a 60s, and if not unpaused, just move on.
            if (timeout - sleep_for) <= 0:
                self.logger.debug("Timed out waiting for READY.")
                return None
            else:
                return self.run(timeout=timeout - sleep_for)

        else:
            # we are READY
            try:
                event = self.execute()
            except exc.JobRequiredError as e:
                self.logger.debug(e, exc_info=True)
                self.logger.warning(e)
                event = events.ErrorOccurred(str(e))
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                event = events.ErrorOccurred(str(e))

        if event:
            self.logger.info(event.display())

        self.latest_event = event
        self._latest_run_at = current_utc_datetime()
        return event

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
        with suppress(AttributeError):
            self.run_thread.join(
                timeout=10
            )  # thread has N seconds to end. If not, something is wrong, like a while loop in execute that isn't stopping.
            if self.run_thread.is_alive():
                self.logger.debug("run_thread still alive!")

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
    duration: float,
    skip_first_run: bool = False,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
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
            skip_first_run=skip_first_run,
            duration=duration,
            **kwargs,
        )

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
@click.option("--duration", default=60.0, help="Time, in minutes, between every monitor check")
@click.option(
    "--skip-first-run",
    type=click.IntRange(min=0, max=1),
    help="Normally algo will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.pass_context
def click_led_automation(ctx, automation_name, duration, skip_first_run):
    """
    Start an LED automation
    """

    with start_led_automation(
        automation_name=automation_name,
        duration=float(duration),
        skip_first_run=bool(skip_first_run),
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    ) as la:
        la.block_until_disconnected()
