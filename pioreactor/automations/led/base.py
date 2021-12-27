# -*- coding: utf-8 -*-
from __future__ import annotations
import time
import json
from threading import Thread
from contextlib import suppress
from typing import Optional, cast


from pioreactor.pubsub import QOS

from pioreactor.utils.timing import RepeatedTimer, current_utc_time
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.background_jobs.led_control import LEDController
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.automations import events
from pioreactor.utils import is_pio_job_running
from pioreactor.types import LED_Channel


class LEDAutomation(BackgroundSubJob):
    """
    This is the super class that LED automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program), and call the `execute` function
    which is what subclasses define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/led_automation/<setting>/set` value

    """

    _latest_growth_rate: Optional[float] = None
    _latest_od: Optional[float] = None
    previous_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None
    latest_od_at: float = 0
    latest_growth_rate_at: float = 0
    latest_settings_started_at: str = current_utc_time()
    latest_settings_ended_at: Optional[str] = None
    edited_channels: set[LED_Channel] = set()
    latest_event: Optional[events.Event] = None
    lastest_run_at: Optional[float] = None
    published_settings = {"duration": {"datatype": "float", "settable": True}}

    automation_name: str
    run_thread: RepeatedTimer | Thread

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of LEDAutomation back to LEDController, so the subclass
        # can be invoked in LEDController.
        if hasattr(cls, "automation_name"):
            LEDController.automations[cls.automation_name] = cls

    def __init__(
        self,
        duration: float,
        skip_first_run: bool = False,
        unit: str = None,
        experiment: str = None,
        **kwargs,
    ) -> None:
        super(LEDAutomation, self).__init__(
            job_name="led_automation", unit=unit, experiment=experiment
        )

        self.skip_first_run = skip_first_run

        self.set_duration(duration)
        self.start_passive_listeners()

        self.logger.info(f"Starting {self.automation_name} LED automation.")

    def set_duration(self, duration: float) -> None:
        self.duration = float(duration)

        if self.lastest_run_at:
            # what's the correct logic when changing from duration N and duration M?
            # - N=20, and it's been 5m since the last run (or initialization). I change to M=30, I should wait M-5 minutes.
            # - N=60, and it's been 50m since last run. I change to M=30, I should run immediately.
            run_after = max(0, (self.duration * 60) - (time.time() - self.lastest_run_at))
        else:
            # there is a race condition here: self.run() will run immediately (see run_immediately), but the state of the job is not READY, since
            # set_duration is run in the __init__ (hence the job is INIT). So we wait 2 seconds for the __init__ to finish, and then run.
            run_after = 2

        self.run_thread = RepeatedTimer(
            self.duration * 60,  # RepeatedTimer uses seconds
            self.run,
            job_name=self.job_name,
            run_immediately=(not self.skip_first_run)
            or (self.lastest_run_at is not None),
            run_after=run_after,
        ).start()

    def run(self) -> Optional[events.Event]:
        # TODO: this should be close to or equal to the function in DosingAutomation
        event: Optional[events.Event]
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return None

        elif self.state != self.READY:

            # solution: wait 25% of duration. If we are still waiting, exit and we will try again next duration.
            counter = 0
            while self.state != self.READY:
                time.sleep(5)
                counter += 1

                if counter > (self.duration * 60 / 4) / 5:
                    event = events.NoEvent(
                        "Waited too long not being in state Ready. Am I stuck? Unpause me? Skipping this run."
                    )
                    break
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
        self.lastest_run_at = time.time()
        return event

    def execute(self) -> Optional[events.Event]:
        pass

    @property
    def most_stale_time(self) -> float:
        return min(self.latest_od_at, self.latest_growth_rate_at)

    def set_led_intensity(self, channel: LED_Channel, intensity: float) -> bool:
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
                channel,
                intensity,
                unit=self.unit,
                experiment=self.experiment,
                pubsub_client=self.pub_client,
                source_of_event=self.job_name,
            )

            if success:
                self.edited_channels.add(channel)
                return True

            time.sleep(0.1)

        self.logger.warning(
            f"Unable to update channel {channel} due to a long lock being on the channel."
        )
        return False

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self.latest_settings_ended_at = current_utc_time()
        self._send_details_to_mqtt()

        with suppress(AttributeError):
            self.run_thread.join()

        for job in self.sub_jobs:
            job.set_state(job.DISCONNECTED)

        for channel in self.edited_channels:
            led_intensity(channel, 0, unit=self.unit, experiment=self.experiment)

        self.clear_mqtt_cache()

    @property
    def latest_growth_rate(self) -> float:
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise ValueError(
                    "`od_reading` and `growth_rate_calculating` should be running."
                )

        # check most stale time
        if (time.time() - self.most_stale_time) > 5 * 60:
            raise ValueError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_od(self) -> float:
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise ValueError(
                    "`od_reading` and `growth_rate_calculating` should be running."
                )

        # check most stale time
        if (time.time() - self.most_stale_time) > 5 * 60:
            raise ValueError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_od)

    def __setattr__(self, name, value) -> None:
        super(LEDAutomation, self).__setattr__(name, value)
        if name in self.published_settings and name != "state":
            self.latest_settings_ended_at = current_utc_time()
            self._send_details_to_mqtt()
            self.latest_settings_started_at = current_utc_time()
            self.latest_settings_ended_at = None

    def _set_growth_rate(self, message) -> None:
        self.previous_growth_rate = self._latest_growth_rate
        self._latest_growth_rate = float(json.loads(message.payload)["growth_rate"])
        self.latest_growth_rate_at = time.time()

    def _set_OD(self, message) -> None:

        self.previous_od = self._latest_od
        self._latest_od = float(json.loads(message.payload)["od_filtered"])
        self.latest_od_at = time.time()

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/led_automation_settings",
            json.dumps(
                {
                    "pioreactor_unit": self.unit,
                    "experiment": self.experiment,
                    "started_at": self.latest_settings_started_at,
                    "ended_at": self.latest_settings_ended_at,
                    "automation": self.automation_name,
                    "settings": json.dumps(
                        {
                            attr: getattr(self, attr, None)
                            for attr in self.published_settings
                            if attr != "state"
                        }
                    ),
                }
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


class LEDAutomationContrib(LEDAutomation):
    automation_name: str
