# -*- coding: utf-8 -*-
from __future__ import annotations
import time
import json
from threading import Thread
from typing import Optional, cast
from contextlib import suppress

from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.actions.add_alt_media import add_alt_media
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import RepeatedTimer, brief_pause, current_utc_time
from pioreactor.automations import events
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.background_jobs.dosing_control import DosingController


class SummableList(list):
    def __add__(self, other):
        return SummableList([s + o for (s, o) in zip(self, other)])

    def __iadd__(self, other):
        return self + other


class DosingAutomation(BackgroundSubJob):
    """
    This is the super class that automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`. This calls the `execute` function, which is what subclasses will define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/dosing_automation/<setting>/set` value

    """

    _latest_growth_rate: Optional[float] = None
    _latest_od: Optional[float] = None
    previous_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None
    latest_od_at: float = 0
    latest_growth_rate_at: float = 0
    latest_event: Optional[events.Event] = None
    latest_settings_started_at: str = current_utc_time()
    latest_settings_ended_at: Optional[str] = None
    latest_run_at: Optional[float] = None
    automation_name: str
    run_thread: RepeatedTimer | Thread
    duration: float | None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of DosingAutomation back to DosingController, so the subclass
        # can be invoked in DosingController.
        if hasattr(cls, "automation_name"):
            DosingController.automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        duration: Optional[float] = None,
        skip_first_run: bool = False,
        **kwargs,
    ) -> None:
        super(DosingAutomation, self).__init__(
            job_name="dosing_automation", unit=unit, experiment=experiment
        )
        self.skip_first_run = skip_first_run

        self.set_duration(duration)
        self.start_passive_listeners()

    def set_duration(self, duration: Optional[float]) -> None:
        if duration:
            self.duration = float(duration)

            with suppress(AttributeError):
                self.run_thread.cancel()  # type: ignore

            if self.latest_run_at:
                # what's the correct logic when changing from duration N and duration M?
                # - N=20, and it's been 5m since the last run (or initialization). I change to M=30, I should wait M-5 minutes.
                # - N=60, and it's been 50m since last run. I change to M=30, I should run immediately.
                run_after = max(
                    0, (self.duration * 60) - (time.time() - self.latest_run_at)
                )
            else:
                # there is a race condition here: self.run() will run immediately (see run_immediately), but the state of the job is not READY, since
                # set_duration is run in the __init__ (hence the job is INIT). So we wait 2 seconds for the __init__ to finish, and then run.
                run_after = 2

            self.run_thread = RepeatedTimer(
                self.duration * 60,
                self.run,
                job_name=self.job_name,
                run_immediately=(not self.skip_first_run)
                or (self.latest_run_at is not None),
                run_after=run_after,
            ).start()

        else:
            self.duration = None
            self.run_thread = Thread(target=self.run, daemon=True)
            self.run_thread.start()

    def run(self) -> Optional[events.Event]:
        event: Optional[events.Event]

        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return None

        elif self.state != self.READY:
            # solution: wait 25% of duration. If we are still waiting, exit and we will try again next duration.
            time_waited = 0
            while self.state != self.READY:

                if self.duration and time_waited > (self.duration * 60 * 0.25):
                    event = events.NoEvent(
                        "Waited too long on sensor data. Skipping this run."
                    )
                    break
                elif self.state == self.DISCONNECTED:
                    return None

                sleep_for = 5
                time.sleep(sleep_for)
                time_waited += sleep_for

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
        self.latest_run_at = time.time()
        return event

    def execute(self) -> Optional[events.Event]:
        # should be defined in subclass
        return events.NoEvent()

    def wait_until_not_sleeping(self) -> bool:
        while self.state == self.SLEEPING:
            brief_pause()
        return True

    def execute_io_action(
        self, alt_media_ml: float = 0, media_ml: float = 0, waste_ml: float = 0
    ) -> SummableList:
        """
        This function recursively reduces the amount to add so that
        we don't end up adding 5ml, and then removing 5ml (this could cause
        overflow). We also want sufficient time to mix, and this procedure will
        slow dosing down.
        """
        volumes_moved = SummableList([0.0, 0.0, 0.0])

        max_ = 0.36  # arbitrary
        if alt_media_ml > max_:
            volumes_moved += self.execute_io_action(
                alt_media_ml=alt_media_ml / 2,
                media_ml=media_ml,
                waste_ml=media_ml + alt_media_ml / 2,
            )
            volumes_moved += self.execute_io_action(
                alt_media_ml=alt_media_ml / 2, media_ml=0, waste_ml=alt_media_ml / 2
            )
        elif media_ml > max_:
            volumes_moved += self.execute_io_action(
                alt_media_ml=0, media_ml=media_ml / 2, waste_ml=media_ml / 2
            )
            volumes_moved += self.execute_io_action(
                alt_media_ml=alt_media_ml,
                media_ml=media_ml / 2,
                waste_ml=alt_media_ml + media_ml / 2,
            )
        else:
            source_of_event = f"{self.job_name}:{self.automation_name}"

            if (
                media_ml > 0
                and (self.state in [self.READY, self.SLEEPING])
                and self.wait_until_not_sleeping()
            ):
                media_moved = add_media(
                    ml=media_ml,
                    source_of_event=source_of_event,
                    unit=self.unit,
                    experiment=self.experiment,
                )
                volumes_moved[0] += media_moved
                brief_pause()

            if (
                alt_media_ml > 0
                and (self.state in [self.READY, self.SLEEPING])
                and self.wait_until_not_sleeping()
            ):  # always check that we are still in a valid state, as state can change between pump runs.
                alt_media_moved = add_alt_media(
                    ml=alt_media_ml,
                    source_of_event=source_of_event,
                    unit=self.unit,
                    experiment=self.experiment,
                )
                volumes_moved[1] += alt_media_moved
                brief_pause()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.

            # remove waste last.
            if (
                waste_ml > 0
                and (self.state in [self.READY, self.SLEEPING])
                and self.wait_until_not_sleeping()
            ):
                waste_moved = remove_waste(
                    ml=waste_ml,
                    source_of_event=source_of_event,
                    unit=self.unit,
                    experiment=self.experiment,
                )
                volumes_moved[2] += waste_moved
                # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
                remove_waste(
                    duration=2,
                    source_of_event=source_of_event,
                    unit=self.unit,
                    experiment=self.experiment,
                )
                brief_pause()

        return volumes_moved

    @property
    def most_stale_time(self) -> float:
        return min(self.latest_od_at, self.latest_growth_rate_at)

    @property
    def latest_growth_rate(self) -> float:
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise RuntimeError(
                    "`od_reading` and `growth_rate_calculating` should be running."
                )

        # check most stale time
        if (time.time() - self.most_stale_time) > 5 * 60:
            raise ValueError(
                f"readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?. Last reading occurred at {self.most_stale_time}, current time is {time.time()}."
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_od(self) -> float:
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading", "growth_rate_calculating"):
                raise RuntimeError(
                    "`od_reading` and `growth_rate_calculating` should be running."
                )

        # check most stale time
        if (time.time() - self.most_stale_time) > 5 * 60:
            raise ValueError(
                f"readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?. Last reading occurred at {self.most_stale_time}, current time is {time.time()}."
            )

        return cast(float, self._latest_od)

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self.latest_settings_ended_at = current_utc_time()
        self._send_details_to_mqtt()

        with suppress(AttributeError):
            self.run_thread.join()

        for job in self.sub_jobs:
            job.set_state("disconnected")

        self.clear_mqtt_cache()

    def __setattr__(self, name, value) -> None:
        super(DosingAutomation, self).__setattr__(name, value)
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
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/dosing_automation_settings",
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


class DosingAutomationContrib(DosingAutomation):
    automation_name: str
