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
from pioreactor.background_jobs.led_control import LEDController
from pioreactor.background_jobs.subjobs import BackgroundSubJob
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime


class LEDAutomationJob(BackgroundSubJob):
    """
    This is the super class that LED automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program), and call the `execute` function
    which is what subclasses define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/led_automation/<setting>/set` value

    """

    automation_name = "led_automation_base"  # is overwritten in subclasses

    published_settings: dict[str, pt.PublishableSetting] = {
        "duration": {"datatype": "float", "settable": True}
    }

    _latest_growth_rate: Optional[float] = None
    _latest_od: Optional[float] = None
    previous_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None

    _latest_settings_ended_at: Optional[str] = None
    _latest_run_at: Optional[datetime] = None

    latest_event: Optional[events.AutomationEvent] = None
    run_thread: RepeatedTimer | Thread

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of LEDAutomation back to LEDController, so the subclass
        # can be invoked in LEDController.
        if hasattr(cls, "automation_name"):
            LEDController.available_automations[cls.automation_name] = cls

    def __init__(
        self,
        duration: float,
        skip_first_run: bool = False,
        unit: str = None,
        experiment: str = None,
        **kwargs,
    ) -> None:
        super(LEDAutomationJob, self).__init__(
            job_name="led_automation", unit=unit, experiment=experiment
        )

        self.skip_first_run = skip_first_run
        self._latest_settings_started_at: str = current_utc_timestamp()
        self.latest_od_at: datetime = datetime.utcnow()
        self.latest_growth_rate_at: datetime = datetime.utcnow()
        self.edited_channels: set[pt.LedChannel] = set()

        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )

        self.set_duration(duration)
        self.start_passive_listeners()

        self.logger.info(f"Starting {self.automation_name} LED automation.")

    def set_duration(self, duration: float) -> None:
        self.duration = duration
        if self._latest_run_at is not None:
            # what's the correct logic when changing from duration N and duration M?
            # - N=20, and it's been 5m since the last run (or initialization). I change to M=30, I should wait M-5 minutes.
            # - N=60, and it's been 50m since last run. I change to M=30, I should run immediately.
            run_after = max(
                0,
                (self.duration * 60) - (datetime.utcnow() - self._latest_run_at).seconds,
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

    def run(self) -> Optional[events.AutomationEvent]:
        # TODO: this should be close to or equal to the function in DosingAutomationJob
        event: Optional[events.AutomationEvent]
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return None

        elif self.state != self.READY:
            # wait a minute, and if not unpaused, just move on.

            time_waited = 0
            sleep_for = 5

            while self.state != self.READY:
                time.sleep(sleep_for)
                time_waited += sleep_for

                if time_waited > 60:
                    return None

            else:
                return self.run()

        else:
            try:
                event = self.execute()
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                event = events.ErrorOccurred()

        if event:
            self.logger.info(str(event))

        self.latest_event = event
        self._latest_run_at = datetime.utcnow()
        return event

    def execute(self) -> Optional[events.AutomationEvent]:
        pass

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_od_at, self.latest_growth_rate_at)

    def set_led_intensity(self, channel: pt.LedChannel, intensity: float) -> bool:
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
        for _ in range(12):
            success = led_intensity(
                {channel: intensity},
                unit=self.unit,
                experiment=self.experiment,
                pubsub_client=self.pub_client,
                source_of_event=self.job_name,
            )

            if success:
                self.edited_channels.add(channel)
                return True

            time.sleep(0.6)

        self.logger.warning(
            f"Unable to update channel {channel} due to a long lock being on the channel."
        )
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
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be Ready."
                )

        # check most stale time
        if (datetime.utcnow() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_od(self) -> float:
        """
        Access the latest normalized optical density.
        """
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be Ready."
                )

        # check most stale time
        if (datetime.utcnow() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_od)

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self._latest_settings_ended_at = current_utc_timestamp()
        self._send_details_to_mqtt()

        with suppress(AttributeError):
            self.run_thread.join()

        led_intensity(
            {channel: 0 for channel in self.edited_channels},
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
        )

    def __setattr__(self, name, value) -> None:
        super(LEDAutomationJob, self).__setattr__(name, value)
        if name in self.published_settings and name not in ["state", "latest_event"]:
            self._latest_settings_ended_at = current_utc_timestamp()
            self._send_details_to_mqtt()
            self._latest_settings_started_at = current_utc_timestamp()
            self._latest_settings_ended_at = None

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = to_datetime(payload.timestamp)

    def _set_OD(self, message: pt.MQTTMessage) -> None:
        self.previous_od = self._latest_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_od = payload.od_filtered
        self.latest_od_at = to_datetime(payload.timestamp)

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
                            if attr not in ["state", "latest_event"]
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
