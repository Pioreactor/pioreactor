# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from threading import Thread
from typing import cast
from typing import Optional

from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.automations import events
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.led_control import LEDController
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
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

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/led_automation/<setting>/set` value

    """

    automation_name = "led_automation_base"  # is overwritten in subclasses
    job_name = "led_automation"

    published_settings: dict[str, pt.PublishableSetting] = {
        "duration": {"datatype": "float", "settable": True}
    }

    _latest_growth_rate: Optional[float] = None
    _latest_normalized_od: Optional[float] = None
    previous_normalized_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None

    _latest_settings_ended_at: Optional[datetime] = None
    _latest_run_at: Optional[datetime] = None

    latest_event: Optional[events.AutomationEvent] = None
    run_thread: RepeatedTimer | Thread

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of LEDAutomation back to LEDController, so the subclass
        # can be invoked in LEDController.
        if (
            hasattr(cls, "automation_name")
            and getattr(cls, "automation_name") != "led_automation_base"
        ):
            LEDController.available_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        duration: float,
        skip_first_run: bool = False,
        **kwargs,
    ) -> None:
        super(LEDAutomationJob, self).__init__(unit, experiment)

        self.skip_first_run = skip_first_run
        self._latest_settings_started_at: datetime = current_utc_datetime()
        self.latest_normalized_od_at: datetime = current_utc_datetime()
        self.latest_growth_rate_at: datetime = current_utc_datetime()
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
            run_after = 2

        self.run_thread = RepeatedTimer(
            self.duration * 60,  # RepeatedTimer uses seconds
            self.run,
            job_name=self.job_name,
            run_immediately=(not self.skip_first_run) or (self._latest_run_at is not None),
            run_after=run_after,
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
            self.logger.info(str(event))

        self.latest_event = event
        self._latest_run_at = current_utc_datetime()
        return event

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at)

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
        attempts = 12
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

            time.sleep(0.6)

        self.logger.warning(f"{self.automation_name} was unable to update channel {channel}.")
        return False

    @property
    def latest_growth_rate(self) -> float:
        """
        Access the latest growth rate.
        """
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be Ready."
                )

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_normalized_od(self) -> float:
        """
        Access the latest normalized optical density.
        """
        # check if None
        if self._latest_normalized_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be Ready."
                )

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_normalized_od)

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self._latest_settings_ended_at = current_utc_datetime()
        self._send_details_to_mqtt()

        with suppress(AttributeError):
            self.run_thread.join()

        led_intensity(
            {channel: 0.0 for channel in self.edited_channels},
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=f"{self.job_name}:{self.automation_name}",
        )

    def __setattr__(self, name, value) -> None:
        super(LEDAutomationJob, self).__setattr__(name, value)
        if name in self.published_settings and name not in ("state", "latest_event"):
            self._latest_settings_ended_at = current_utc_datetime()
            self._send_details_to_mqtt()
            self._latest_settings_started_at = current_utc_datetime()
            self._latest_settings_ended_at = None

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = payload.timestamp

    def _set_OD(self, message: pt.MQTTMessage) -> None:
        self.previous_normalized_od = self._latest_normalized_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_normalized_od = payload.od_filtered
        self.latest_normalized_od_at = payload.timestamp

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/led_automation_settings",
            encode(
                structs.AutomationSettings(
                    pioreactor_unit=self.unit,
                    experiment=self.experiment,
                    started_at=self._latest_settings_started_at,
                    ended_at=self._latest_settings_ended_at,
                    automation_name=self.automation_name,
                    settings=encode(
                        {
                            attr: getattr(self, attr, None)
                            for attr in self.published_settings
                            if attr not in ("state", "latest_event")
                        }
                    ),
                )
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self._set_OD,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/od_filtered",
        )
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
        )


class LEDAutomationJobContrib(LEDAutomationJob):
    automation_name: str
