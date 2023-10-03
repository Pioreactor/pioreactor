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

from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.automations import events
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.dosing_control import DosingController
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import SummableDict
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer


def brief_pause() -> float:
    d = 5.0
    time.sleep(d)
    return d


def briefer_pause() -> float:
    d = 0.05
    time.sleep(d)
    return d


def pause_between_subdoses() -> float:
    d = float(
        config.get("dosing_automation.config", "pause_between_subdoses_seconds", fallback=5.0)
    )
    time.sleep(d)
    return d


"""
Calculators should ideally be state-less
"""


class ThroughputCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media. Useful for knowing how much media
    has been spent, so that triggers can be set up to replace media stock.
    """

    @staticmethod
    def update(
        dosing_event: structs.DosingEvent,
        current_media_throughput: float,
        current_alt_media_throughput: float,
    ) -> tuple[float, float]:
        volume, event = float(dosing_event.volume_change), dosing_event.event
        if event == "add_media":
            current_media_throughput += volume
        elif event == "add_alt_media":
            current_alt_media_throughput += volume
        elif event == "remove_waste":
            pass
        else:
            raise ValueError("Unknown event type")

        return (current_media_throughput, current_alt_media_throughput)


class VialVolumeCalculator:
    max_volume = config.getfloat("bioreactor", "max_volume_ml")

    @classmethod
    def update(cls, new_dosing_event: structs.DosingEvent, current_vial_volume: float) -> float:
        assert current_vial_volume >= 0
        volume, event = float(new_dosing_event.volume_change), new_dosing_event.event
        if event == "add_media":
            return current_vial_volume + volume
        elif event == "add_alt_media":
            return current_vial_volume + volume
        elif event == "remove_waste":
            if new_dosing_event.source_of_event == "manually":
                # we assume the user has extracted what they want, regardless of level or tube height.
                return max(current_vial_volume - volume, 0.0)
            elif current_vial_volume <= cls.max_volume:
                # if the current volume is less than the outflow tube, no liquid is removed
                return current_vial_volume
            else:
                # since we do some additional "removing" after adding, we don't want to
                # count that as being removed (total volume is limited by position of outflow tube).
                # hence we keep an lowerbound here.
                return max(current_vial_volume - volume, cls.max_volume)
        else:
            raise ValueError("Unknown event type")


class AltMediaFractionCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.
    State-less.
    """

    @classmethod
    def update(
        cls,
        new_dosing_event: structs.DosingEvent,
        current_alt_media_fraction: float,
        current_vial_volume: float,
    ) -> float:
        assert 0.0 <= current_alt_media_fraction <= 1.0
        volume, event = float(new_dosing_event.volume_change), new_dosing_event.event

        if event == "add_media":
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, volume, 0, current_vial_volume
            )
        elif event == "add_alt_media":
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, 0, volume, current_vial_volume
            )
        elif event == "remove_waste":
            return current_alt_media_fraction
        else:
            # if the users added, ex, "add_salty_media", well this is the same as adding media (from the POV of alt_media_fraction)
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, volume, 0, current_vial_volume
            )

    @classmethod
    def _update_alt_media_fraction(
        cls,
        current_alt_media_fraction: float,
        media_delta: float,
        alt_media_delta: float,
        current_vial_volume: float,
    ) -> float:
        assert media_delta >= 0
        assert alt_media_delta >= 0
        total_addition = media_delta + alt_media_delta

        return (current_alt_media_fraction * current_vial_volume + alt_media_delta) / (
            current_vial_volume + total_addition
        )


class DosingAutomationJob(AutomationJob):
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

    previous_normalized_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None
    previous_od: Optional[dict[pt.PdChannel, float]] = None
    # latest_normalized_od: float  // defined as properties
    # latest_growth_rate: float  // defined as properties
    # latest_od: dict[pt.PdChannel, float]  // defined as properties
    _latest_growth_rate: Optional[float] = None
    _latest_normalized_od: Optional[float] = None
    _latest_od: Optional[dict[pt.PdChannel, float]] = None

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
    vial_volume: float  # amount in the vial
    MAX_VIAL_VOLUME_TO_WARN: float = config.getfloat(
        "dosing_automation.config", "max_volume_to_warn", fallback=17.0
    )
    MAX_VIAL_VOLUME_TO_STOP: float = config.getfloat(
        "dosing_automation.config", "max_volume_to_stop", fallback=18.0
    )

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
        initial_alt_media_fraction: float = config.getfloat(
            "bioreactor", "initial_alt_media_fraction", fallback=0.0
        ),
        initial_vial_volume: float = config.getfloat(
            "bioreactor", "initial_volume_ml", fallback=14
        ),
        **kwargs,
    ) -> None:
        super(DosingAutomationJob, self).__init__(unit, experiment)
        self.skip_first_run = skip_first_run

        self._latest_settings_started_at = current_utc_datetime()
        self.latest_normalized_od_at = current_utc_datetime()
        self.latest_growth_rate_at = current_utc_datetime()
        self.latest_od_at = current_utc_datetime()

        self._init_alt_media_fraction(float(initial_alt_media_fraction))
        self._init_volume_throughput()
        self._init_vial_volume(float(initial_vial_volume))

        self.set_duration(duration)

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

    def run(self, timeout: float = 60.0) -> Optional[events.AutomationEvent]:
        """
        Parameters
        -----------
        timeout: float
            if the job is not in a READY state after timeout seconds, skip calling `execute` this period.
            Default 60s.

        """
        event: Optional[events.AutomationEvent]

        self._latest_run_at = current_utc_datetime()

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
            # we are in READY
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
        return event

    def block_until_not_sleeping(self) -> bool:
        while self.state == self.SLEEPING:
            brief_pause()
        return True

    def execute_io_action(
        self,
        waste_ml: float = 0,
        media_ml: float = 0,
        alt_media_ml: float = 0,
        **other_pumps_ml: float,
    ) -> SummableDict:
        """
        This function recursively reduces the amount to add so that we don't end up adding 5ml,
        and then removing 5ml (this could cause vial overflow). Instead we add 0.5ml, remove 0.5ml,
        add 0.5ml, remove 0.5ml, and so on. We also want sufficient time to mix, and this procedure
        will slow dosing down.


        Users can call additional pumps (other than media and alt_media) by providing them as kwargs. Ex:

        > dc.execute_io_action(waste_ml=2, media_ml=1, salt_media_ml=0.5, media_from_sigma_ml=0.5)

        It's required that a named pump function is present to. In the example above, we would need the following defined:

        > dc.add_salt_media_to_bioreactor(...)
        > dc.add_media_from_sigma_to_bioreactor(...)

        Specifically, if you enter a kwarg `<name>_ml`, you need a function `add_<name>_to_bioreactor`. The pump function
        should have signature equal to pioreactor.types.DosingProgram.



        Note
        ------
        If alt_media_ml and media_ml are non-zero, we keep their ratio equal for each
        sub-call. This keeps the ratio of alt_media to media the same in the vial.

        A problem is if the there is skew in the different mLs, then it's possible that one or more pumps
        most dose a very small amount, where our pumps have poor accuracy.


        Returns
        ---------
        A dict of volumes that were moved, in mL. This may be different than the request mLs, if a error in a pump occurred.

        """
        if not all(other_pump_ml.endswith("_ml") for other_pump_ml in other_pumps_ml.keys()):
            raise ValueError(
                "all kwargs should end in `_ml`. Example: `execute_io_action(salty_media_ml=1.0)`"
            )

        all_pumps_ml = {**{"media_ml": media_ml, "alt_media_ml": alt_media_ml}, **other_pumps_ml}

        sum_of_volumes = sum(ml for ml in all_pumps_ml.values())

        if not (waste_ml >= sum_of_volumes):
            raise ValueError(
                "Not removing enough waste: waste_ml should be greater than sum of dosed ml"
            )

        max_ = 0.75  # arbitrary, but should be some value that the pump is well calibrated for. TODO: should this be a constant on the class?
        volumes_moved = SummableDict(waste_ml=0.0, **{p: 0.0 for p in all_pumps_ml})
        source_of_event = f"{self.job_name}:{self.automation_name}"

        if sum_of_volumes > max_:
            volumes_moved += self.execute_io_action(
                waste_ml=sum_of_volumes / 2,
                **{pump: volume_ml / 2 for pump, volume_ml in all_pumps_ml.items()},
            )
            volumes_moved += self.execute_io_action(
                waste_ml=sum_of_volumes / 2,
                **{pump: volume_ml / 2 for pump, volume_ml in all_pumps_ml.items()},
            )

        else:
            # iterate through pumps, and dose required amount. First media, then alt_media, then any others, then waste.
            for pump, volume_ml in all_pumps_ml.items():
                if (self.vial_volume + volume_ml) >= self.MAX_VIAL_VOLUME_TO_STOP:
                    self.logger.error(
                        f"Stopping all pumping since {self.vial_volume} + {volume_ml} mL is beyond safety threshold {self.MAX_VIAL_VOLUME_TO_STOP} mL."
                    )
                    self.set_state(self.SLEEPING)

                if (
                    (volume_ml > 0)
                    and (self.state in (self.READY,))
                    and self.block_until_not_sleeping()
                ):
                    pump_function = getattr(self, f"add_{pump.removesuffix('_ml')}_to_bioreactor")

                    volume_moved_ml = pump_function(
                        unit=self.unit,
                        experiment=self.experiment,
                        ml=volume_ml,
                        source_of_event=source_of_event,
                    )
                    volumes_moved[pump] += volume_moved_ml
                    pause_between_subdoses()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.

            # remove waste last.
            if waste_ml > 0 and (self.state in (self.READY,)) and self.block_until_not_sleeping():
                waste_moved_ml = self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=waste_ml,
                    source_of_event=source_of_event,
                )
                volumes_moved["waste_ml"] += waste_moved_ml

                if waste_moved_ml < waste_ml:
                    self.logger.warning(
                        "Waste was under-removed. Risk of overflow. Is the waste pump working?"
                    )

                briefer_pause()
                # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
                self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=waste_ml
                    * config.getfloat(
                        "dosing_automation.config", "waste_removal_multiplier", fallback=2.0
                    ),
                    source_of_event=source_of_event,
                )
                briefer_pause()

        return volumes_moved

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at, self.latest_od_at)

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
        if (current_utc_datetime() - self.latest_od_at).seconds > 5 * 60:
            raise exc.JobRequiredError(
                f"readings are too stale (over 5 minutes old) - is `od_reading` running?. Last reading occurred at {self.latest_od_at}."
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
        if name in self.published_settings and name not in (
            "state",
            "alt_media_fraction",
            "media_throughput",
            "alt_media_throughput",
            "latest_event",
            "vial_volume",
        ):
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
                            not in (
                                "state",
                                "alt_media_fraction",
                                "media_throughput",
                                "vial_volume",
                                "alt_media_throughput",
                                "latest_event",
                            )
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
        self._update_vial_volume(dosing_event)

    def _update_alt_media_fraction(self, dosing_event: structs.DosingEvent) -> None:
        self.alt_media_fraction = AltMediaFractionCalculator.update(
            dosing_event, self.alt_media_fraction, self.vial_volume
        )

        # add to cache
        with local_persistant_storage("alt_media_fraction") as cache:
            cache[self.experiment] = self.alt_media_fraction

    def _update_vial_volume(self, dosing_event: structs.DosingEvent) -> None:
        self.vial_volume = VialVolumeCalculator.update(dosing_event, self.vial_volume)

        # add to cache
        with local_persistant_storage("vial_volume") as cache:
            cache[self.experiment] = self.vial_volume

        if self.vial_volume >= self.MAX_VIAL_VOLUME_TO_WARN:
            self.logger.warning(
                f"Vial is calculated to have a volume of {self.vial_volume} mL. Is this expected?"
            )

    def _update_throughput(self, dosing_event: structs.DosingEvent) -> None:
        (
            self.media_throughput,
            self.alt_media_throughput,
        ) = ThroughputCalculator.update(
            dosing_event, self.media_throughput, self.alt_media_throughput
        )

        # add to cache
        with local_persistant_storage("alt_media_throughput") as cache:
            cache[self.experiment] = self.alt_media_throughput

        with local_persistant_storage("media_throughput") as cache:
            cache[self.experiment] = self.media_throughput

    def _init_alt_media_fraction(self, initial_alt_media_fraction: float) -> None:
        assert 0 <= initial_alt_media_fraction <= 1
        self.add_to_published_settings(
            "alt_media_fraction",
            {
                "datatype": "float",
                "settable": False,
            },
        )

        with local_persistant_storage("alt_media_fraction") as cache:
            self.alt_media_fraction = cache.get(self.experiment, initial_alt_media_fraction)

        return

    def _init_vial_volume(self, initial_vial_volume: float):
        assert initial_vial_volume >= 0

        self.add_to_published_settings(
            "vial_volume",
            {
                "datatype": "float",
                "settable": False,  # modify using dosing_events, ex: pio run add_media --ml 1 --manually
                "unit": "mL",
            },
        )

        with local_persistant_storage("vial_volume") as cache:
            self.vial_volume = cache.get(self.experiment, initial_vial_volume)

        return

    def _init_volume_throughput(self):
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

        return

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
