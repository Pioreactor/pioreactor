# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from functools import partial
from threading import Thread
from typing import Any
from typing import cast
from typing import Optional
from typing import Type

from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.automations import events
from pioreactor.background_jobs.dosing_control import DosingController
from pioreactor.background_jobs.subjobs import BackgroundSubJob
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import SummableList
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer


def brief_pause() -> None:
    time.sleep(5.0)
    return


class ThroughputCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media. Useful for knowing how much media
    has been spent, so that triggers can be set up to replace media stock.

    """

    @staticmethod
    def update(
        dosing_event: structs.DosingEvent,
        current_media_volume: float,
        current_alt_media_volume: float,
    ) -> tuple[float, float]:
        volume, event = float(dosing_event.volume_change), dosing_event.event
        if event == "add_media":
            current_media_volume += volume
        elif event == "add_alt_media":
            current_alt_media_volume += volume
        elif event == "remove_waste":
            pass
        else:
            raise ValueError("Unknown event type")

        return (current_media_volume, current_alt_media_volume)


class AltMediaCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.

    1. State-less. Something else needs to record current_alt_media_fraction
    2. Assumes constant volume throughout.

    """

    vial_volume = config.getfloat("bioreactor", "volume_ml")

    @classmethod
    def update(cls, dosing_event: structs.DosingEvent, current_alt_media_fraction: float) -> float:
        assert 0.0 <= current_alt_media_fraction <= 1.0
        volume, event = float(dosing_event.volume_change), dosing_event.event
        if event == "add_media":
            return cls._update_alt_media_fraction(current_alt_media_fraction, volume, 0)
        elif event == "add_alt_media":
            return cls._update_alt_media_fraction(current_alt_media_fraction, 0, volume)
        elif event == "remove_waste":
            return current_alt_media_fraction
        else:
            raise ValueError("Unknown event type")

    @classmethod
    def _update_alt_media_fraction(
        cls,
        current_alt_media_fraction: float,
        media_delta: float,
        alt_media_delta: float,
    ) -> float:
        assert media_delta >= 0
        assert alt_media_delta >= 0

        total_delta = media_delta + alt_media_delta

        # current mL
        alt_media_ml = cls.vial_volume * current_alt_media_fraction
        media_ml = cls.vial_volume * (1 - current_alt_media_fraction)

        # remove
        alt_media_ml = alt_media_ml * (1 - total_delta / cls.vial_volume)
        media_ml = media_ml * (1 - total_delta / cls.vial_volume)

        # add (alt) media
        alt_media_ml = alt_media_ml + alt_media_delta
        media_ml = media_ml + media_delta

        return alt_media_ml / cls.vial_volume


class DosingAutomationJob(BackgroundSubJob):
    """
    This is the super class that automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`. This calls the `execute` function, which is what subclasses will define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/dosing_automation/<setting>/set` value

    """

    automation_name = "dosing_automation_base"  # is overwritten in subclasses
    job_name = "dosing_automation"
    published_settings: dict[str, pt.PublishableSetting] = {}

    _latest_growth_rate: Optional[float] = None
    _latest_normalized_od: Optional[float] = None
    _latest_od: Optional[dict[pt.PdChannel, float]] = None
    previous_normalized_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None
    previous_od: Optional[dict[pt.PdChannel, float]] = None

    latest_event: Optional[events.AutomationEvent] = None
    _latest_settings_ended_at: Optional[datetime] = None
    _latest_run_at: Optional[datetime] = None
    run_thread: RepeatedTimer | Thread
    duration: float | None

    # overwrite to use your own dosing programs.
    # interface must look like types.DosingProgram
    add_media_to_bioreactor: pt.DosingProgram = partial(
        add_media, duration=None, calibration=None, continuously=False
    )
    remove_waste_from_bioreactor: pt.DosingProgram = partial(
        remove_waste, duration=None, calibration=None, continuously=False
    )
    add_alt_media_to_bioreactor: pt.DosingProgram = partial(
        add_alt_media, duration=None, calibration=None, continuously=False
    )

    # dosing metrics that are available, and published to MQTT
    alt_media_fraction: float  # fraction of the vial that is alt-media (vs regular media).
    media_throughput: float  # amount of media that has been expelled
    alt_media_throughput: float  # amount of alt-media that has been expelled

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of DosingAutomationJob back to DosingController, so the subclass
        # can be invoked in DosingController.
        if (
            hasattr(cls, "automation_name")
            and getattr(cls, "automation_name") != "dosing_automation_base"
        ):
            DosingController.available_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        duration: Optional[float] = None,
        skip_first_run: bool = False,
        **kwargs,
    ) -> None:
        super(DosingAutomationJob, self).__init__(unit=unit, experiment=experiment)
        self.skip_first_run = skip_first_run
        self._latest_settings_started_at = current_utc_datetime()
        self.latest_normalized_od_at = current_utc_datetime()
        self.latest_growth_rate_at = current_utc_datetime()
        self.latest_od_at = current_utc_datetime()

        self._alt_media_fraction_calculator = self._init_alt_media_fraction_calculator()
        self._volume_throughput_calculator = self._init_volume_throughput_calculator()

        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )

        self.set_duration(duration)

        self.start_passive_listeners()

    def set_duration(self, duration: Optional[float]) -> None:
        if duration:
            self.duration = float(duration)

            with suppress(AttributeError):
                self.run_thread.cancel()  # type: ignore

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
                self.duration * 60,
                self.run,
                job_name=self.job_name,
                run_immediately=(not self.skip_first_run) or (self._latest_run_at is not None),
                run_after=run_after,
            ).start()

        else:
            self.duration = None
            self.run_thread = Thread(target=self.run, daemon=True)
            self.run_thread.start()

    def run(self) -> Optional[events.AutomationEvent]:
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

    def execute(self) -> Optional[events.AutomationEvent]:
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
        This function recursively reduces the amount to add so that we don't end up adding 5ml,
        and then removing 5ml (this could cause overflow).
        Instead we add 0.5ml, remove 0.5ml, add 0.5ml, remove 0.5ml, etc.

        We also want sufficient time to mix, and this procedure will slow dosing down.
        """
        volumes_moved = SummableList([0.0, 0.0, 0.0])  # media, alt_media, waste

        max_ = 0.625  # arbitrary (2.5/4), but should be some value that the pump is well calibrated for
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
                media_moved = self.add_media_to_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=media_ml,
                    source_of_event=source_of_event,
                )
                volumes_moved[0] += media_moved
                brief_pause()

            if (
                alt_media_ml > 0
                and (self.state in [self.READY, self.SLEEPING])
                and self.wait_until_not_sleeping()
            ):  # always check that we are still in a valid state, as state can change between pump runs.
                alt_media_moved = self.add_alt_media_to_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=alt_media_ml,
                    source_of_event=source_of_event,
                )
                volumes_moved[1] += alt_media_moved
                brief_pause()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.

            # remove waste last.
            if (
                waste_ml > 0
                and (self.state in [self.READY, self.SLEEPING])
                and self.wait_until_not_sleeping()
            ):
                waste_moved = self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=waste_ml,
                    source_of_event=source_of_event,
                )
                volumes_moved[2] += waste_moved

                # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
                self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=waste_ml * 2,
                    source_of_event=source_of_event,
                )

        return volumes_moved

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at)

    @property
    def latest_growth_rate(self) -> float:
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
                f"readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?. Last reading occurred at {self.most_stale_time}."
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_normalized_od(self) -> float:
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
                f"readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?. Last reading occurred at {self.most_stale_time}."
            )

        return cast(float, self._latest_normalized_od)

    @property
    def latest_od(self) -> dict[pt.PdChannel, float]:
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading"):
                raise exc.JobRequiredError("`od_reading` should be Ready.")

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                f"readings are too stale (over 5 minutes old) - is `od_reading` running?. Last reading occurred at {self.most_stale_time}."
            )

        assert self._latest_od is not None
        return self._latest_od

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self._latest_settings_ended_at = current_utc_datetime()
        self._send_details_to_mqtt()

        with suppress(AttributeError):
            self.run_thread.join()

    def __setattr__(self, name: str, value: Any) -> None:
        super(DosingAutomationJob, self).__setattr__(name, value)
        if name in self.published_settings and name not in [
            "state",
            "alt_media_fraction",
            "media_throughput",
            "alt_media_throughput",
            "latest_event",
        ]:
            self._latest_settings_ended_at = current_utc_datetime()
            self._send_details_to_mqtt()
            self._latest_settings_started_at = current_utc_datetime()
            self._latest_settings_ended_at = None

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = payload.timestamp

    def _set_normalized_od(self, message: pt.MQTTMessage) -> None:
        self.previous_normalized_od = self._latest_normalized_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_normalized_od = payload.od_filtered
        self.latest_normalized_od_at = payload.timestamp

    def _set_ods(self, message: pt.MQTTMessage) -> None:
        self.previous_od = self._latest_od
        payload = decode(message.payload, type=structs.ODReadings)
        self._latest_od: dict[pt.PdChannel, float] = {c: payload.ods[c].od for c in payload.ods}
        self.latest_od_at = payload.timestamp

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/dosing_automation_settings",
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
                            if attr
                            not in [
                                "state",
                                "alt_media_fraction",
                                "media_throughput",
                                "alt_media_throughput",
                                "latest_event",
                            ]
                        }
                    ),
                )
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def _update_dosing_metrics(self, message: pt.MQTTMessage) -> None:
        dosing_event = decode(message.payload, type=structs.DosingEvent)
        self._update_alt_media_fraction(dosing_event)
        self._update_throughput(dosing_event)

    def _update_alt_media_fraction(self, dosing_event: structs.DosingEvent) -> None:
        self.alt_media_fraction = self._alt_media_fraction_calculator.update(
            dosing_event, self.alt_media_fraction
        )
        # add to cache
        with local_persistant_storage("alt_media_fraction") as cache:
            cache[self.experiment] = self.alt_media_fraction

    def _update_throughput(self, dosing_event: structs.DosingEvent) -> None:
        (
            self.media_throughput,
            self.alt_media_throughput,
        ) = self._volume_throughput_calculator.update(
            dosing_event, self.media_throughput, self.alt_media_throughput
        )

        # add to cache
        with local_persistant_storage("alt_media_throughput") as cache:
            cache[self.experiment] = self.alt_media_throughput

        with local_persistant_storage("media_throughput") as cache:
            cache[self.experiment] = self.media_throughput

    def _init_alt_media_fraction_calculator(self) -> Type[AltMediaCalculator]:
        self.add_to_published_settings(
            "alt_media_fraction",
            {
                "datatype": "float",
                "settable": False,
            },
        )

        with local_persistant_storage("alt_media_fraction") as cache:
            self.alt_media_fraction = cache.get(self.experiment, 0.0)

        return AltMediaCalculator

    def _init_volume_throughput_calculator(self) -> Type[ThroughputCalculator]:
        self.add_to_published_settings(
            "alt_media_throughput",
            {
                "datatype": "float",
                "settable": True,  # settable because in the future, the UI may "reset" these values to 0.
                "unit": "mL",
            },
        )
        self.add_to_published_settings(
            "media_throughput",
            {
                "datatype": "float",
                "settable": True,
                "unit": "mL",
            },
        )

        with local_persistant_storage("alt_media_throughput") as cache:
            self.alt_media_throughput = cache.get(self.experiment, 0.0)

        with local_persistant_storage("media_throughput") as cache:
            self.media_throughput = cache.get(self.experiment, 0.0)

        return ThroughputCalculator

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self._set_normalized_od,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/od_filtered",
        )
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
        )
        self.subscribe_and_callback(
            self._set_ods,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
        )
        self.subscribe_and_callback(
            self._update_dosing_metrics,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
        )


class DosingAutomationJobContrib(DosingAutomationJob):
    automation_name: str
