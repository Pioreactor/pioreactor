# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from functools import partial
from threading import Thread
from typing import Optional

import click
from msgspec.json import decode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.automations import events
from pioreactor.automations.base import AutomationJob
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import SummableDict
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer


class classproperty(property):
    def __get__(self, obj, objtype=None):
        return self.fget(objtype)


def brief_pause() -> float:
    d = 5.0
    time.sleep(d)
    return d


def briefer_pause() -> float:
    d = 0.05
    time.sleep(d)
    return d


def pause_between_subdoses() -> float:
    d = float(config.get("dosing_automation.config", "pause_between_subdoses_seconds", fallback=5.0))
    time.sleep(d)
    return d


def is_20ml() -> bool:
    return whoami.get_pioreactor_model() == "pioreactor_20ml"


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


class LiquidVolumeCalculator:
    @classmethod
    def update(
        cls, new_dosing_event: structs.DosingEvent, current_liquid_volume: float, max_volume: float
    ) -> float:
        assert current_liquid_volume >= 0
        assert max_volume >= 0
        volume, event = float(new_dosing_event.volume_change), new_dosing_event.event
        if event == "add_media":
            return max(current_liquid_volume + volume, 0)
        elif event == "add_alt_media":
            return max(current_liquid_volume + volume, 0)
        elif event == "remove_waste":
            if new_dosing_event.source_of_event == "manually":
                # we assume the user has extracted what they want, regardless of level or tube height.
                return max(current_liquid_volume - volume, 0.0)
            elif current_liquid_volume <= max_volume:
                # if the current volume is less than the outflow tube, no liquid is removed
                return max(current_liquid_volume, 0)
            else:
                # since we do some additional "removing" after adding, we don't want to
                # count that as being removed (total volume is limited by position of outflow tube).
                # hence we keep an lowerbound here.
                return max(current_liquid_volume - volume, max_volume, 0)
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
        current_liquid_volume: float,
    ) -> float:
        assert 0.0 <= current_alt_media_fraction <= 1.0
        assert current_liquid_volume >= 0
        volume, event = float(new_dosing_event.volume_change), new_dosing_event.event

        if event == "add_media":
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, volume, 0, current_liquid_volume
            )
        elif event == "add_alt_media":
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, 0, volume, current_liquid_volume
            )
        elif event == "remove_waste":
            return current_alt_media_fraction
        else:
            # if the users added, ex, "add_salty_media", well this is the same as adding media (from the POV of alt_media_fraction)
            return cls._update_alt_media_fraction(
                current_alt_media_fraction, volume, 0, current_liquid_volume
            )

    @classmethod
    def _update_alt_media_fraction(
        cls,
        current_alt_media_fraction: float,
        media_delta: float,
        alt_media_delta: float,
        current_liquid_volume: float,
    ) -> float:
        total_addition = media_delta + alt_media_delta

        return clamp(
            0.0,
            round(
                (current_alt_media_fraction * current_liquid_volume + alt_media_delta)
                / (current_liquid_volume + total_addition),
                10,
            ),
            1.0,
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
    published_settings: dict[
        str, pt.PublishableSetting
    ] = {}  # see methods in init for dynamic additions, like liquid_volume

    latest_event: Optional[events.AutomationEvent] = None
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
    liquid_volume: float  # amount in the vial

    @classproperty
    def MAX_VIAL_VOLUME_TO_STOP(cls) -> float:
        return 18.0 if is_20ml() else 38.0

    @classproperty
    def MAX_VIAL_VOLUME_TO_WARN(cls) -> float:
        return 0.95 * cls.MAX_VIAL_VOLUME_TO_STOP

    MAX_SUBDOSE = config.getfloat(
        "dosing_automation.config", "max_subdose", fallback=1.0
    )  # arbitrary, but should be some value that the pump is well calibrated for.

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of DosingAutomationJob
        if hasattr(cls, "automation_name") and getattr(cls, "automation_name") != "dosing_automation_base":
            available_dosing_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        duration: Optional[float] = None,
        skip_first_run: bool = False,
        initial_alt_media_fraction: float | None = None,
        initial_liquid_volume_ml: float | None = None,
        max_volume_ml: float | None = None,
        **kwargs,
    ) -> None:
        super(DosingAutomationJob, self).__init__(unit, experiment)

        self.add_to_published_settings(
            "duration",
            {
                "datatype": "float",
                "settable": True,
                "unit": "min",
            },
        )

        self.skip_first_run = skip_first_run

        self._init_alt_media_fraction(initial_alt_media_fraction)
        self._init_volume_throughput()
        self._init_liquid_volume(initial_liquid_volume_ml, max_volume_ml)

        self.set_duration(duration)

        if not is_pio_job_running("stirring"):
            self.logger.warning(
                "It's recommended to have stirring on to improve mixing during dosing events."
            )

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
                run_after = 2.0

            self.run_thread = RepeatedTimer(
                self.duration * 60,
                self.run,
                job_name=self.job_name,
                run_immediately=(not self.skip_first_run) or (self._latest_run_at is not None),
                run_after=run_after,
                logger=self.logger,
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
                if event:
                    self.logger.info(event.display())

            except exc.JobRequiredError as e:
                self.logger.debug(e, exc_info=True)
                self.logger.warning(e)
                event = events.ErrorOccurred(str(e))
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                event = events.ErrorOccurred(str(e))

        self.latest_event = event
        return event

    def block_until_not_sleeping(self) -> bool:
        while self.state == self.SLEEPING:
            brief_pause()
        return True

    def execute_io_action(
        self,
        waste_ml: float = 0.0,
        **all_pumps_ml: float,
    ) -> SummableDict:
        """
        This function recursively reduces the amount to add so that we don't end up adding 5ml,
        and then removing 5ml (this could cause vial overflow). Instead we add 0.5ml, remove 0.5ml,
        add 0.5ml, remove 0.5ml, and so on. We also want sufficient time to mix, and this procedure
        will slow dosing down.


        Users can call additional pumps by providing them as kwargs. Ex:

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
        must dose a very small amount, where our pumps have poor accuracy.


        Returns
        ---------
        A dict of volumes that were moved, in mL. This may be different than the request mLs, if a error in a pump occurred.

        """
        if not all(other_pump_ml.endswith("_ml") for other_pump_ml in all_pumps_ml.keys()):
            raise ValueError(
                "all kwargs should end in `_ml`. Example: `execute_io_action(salty_media_ml=1.0)`"
            )

        sum_of_volumes = sum(ml for ml in all_pumps_ml.values())
        if not (waste_ml >= sum_of_volumes - 1e-9):
            # why close? account for floating point imprecision, ex: .6299999999999999 != 0.63
            raise ValueError(
                "Not removing enough waste: waste_ml should be greater than or equal to sum of all dosed ml"
            )

        volumes_moved = SummableDict(waste_ml=0.0, **{p: 0.0 for p in all_pumps_ml})
        source_of_event = f"{self.job_name}:{self.automation_name}"

        if sum_of_volumes > self.MAX_SUBDOSE:
            volumes_moved += self.execute_io_action(
                waste_ml=sum_of_volumes / 2,
                **{pump: volume_ml / 2 for pump, volume_ml in all_pumps_ml.items()},
            )
            volumes_moved += self.execute_io_action(
                waste_ml=sum_of_volumes / 2,
                **{pump: volume_ml / 2 for pump, volume_ml in all_pumps_ml.items()},
            )

        else:
            # iterate through pumps, and dose required amount. First *_media, then waste.
            for pump, volume_ml in all_pumps_ml.items():
                if (self.liquid_volume + volume_ml) >= self.MAX_VIAL_VOLUME_TO_STOP:
                    self.logger.error(
                        f"Pausing all pumping since {self.liquid_volume} + {volume_ml} mL is beyond safety threshold {self.MAX_VIAL_VOLUME_TO_STOP} mL."
                    )
                    self.set_state(self.SLEEPING)
                    return volumes_moved

                if (
                    (volume_ml > 0)
                    and self.block_until_not_sleeping()
                    and (self.state in (self.READY,))
                    and not self._blocking_event.is_set()
                ):
                    pump_function = getattr(self, f"add_{pump.removesuffix('_ml')}_to_bioreactor")

                    volumes_moved[pump] += pump_function(
                        unit=self.unit,
                        experiment=self.experiment,
                        ml=volume_ml,
                        source_of_event=source_of_event,
                        mqtt_client=self.pub_client,
                        logger=self.logger,
                    )
                    pause_between_subdoses()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.

            # remove waste last.
            if (
                waste_ml > 0
                and self.block_until_not_sleeping()
                and (self.state in (self.READY,))
                and not self._blocking_event.is_set()
            ):
                volumes_moved["waste_ml"] += self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=waste_ml,
                    source_of_event=source_of_event,
                    mqtt_client=self.pub_client,
                    logger=self.logger,
                )
                briefer_pause()

            # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
            # check exit conditions again!
            extra_waste_ml = waste_ml * config.getfloat(
                "dosing_automation.config", "waste_removal_multiplier", fallback=2.0
            )
            if (
                extra_waste_ml > 0
                and self.block_until_not_sleeping()
                and (self.state in (self.READY,))
                and not self._blocking_event.is_set()
            ):
                self.remove_waste_from_bioreactor(
                    unit=self.unit,
                    experiment=self.experiment,
                    ml=extra_waste_ml,
                    source_of_event=source_of_event,
                    mqtt_client=self.pub_client,
                    logger=self.logger,
                )
                briefer_pause()

        if volumes_moved["waste_ml"] < waste_ml:
            self.logger.warning(
                f"Waste was under-removed. Expected to remove {waste_ml} ml, only removed {volumes_moved['waste_ml']} ml."
            )

        return volumes_moved

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        with suppress(AttributeError):
            self.run_thread.join(
                timeout=5
            )  # thread has N seconds to end. If not, something is wrong, like a while loop in execute that isn't stopping.
            if self.run_thread.is_alive():
                self.logger.debug("run_thread still alive!")

    def _update_dosing_metrics(self, message: pt.MQTTMessage) -> None:
        dosing_event = decode(message.payload, type=structs.DosingEvent)
        self._update_alt_media_fraction(dosing_event)
        self._update_throughput(dosing_event)
        self._update_liquid_volume(dosing_event)

    def _update_alt_media_fraction(self, dosing_event: structs.DosingEvent) -> None:
        self.alt_media_fraction = AltMediaFractionCalculator.update(
            dosing_event, self.alt_media_fraction, self.liquid_volume
        )

        # add to cache
        with local_persistent_storage("alt_media_fraction") as cache:
            cache[self.experiment] = self.alt_media_fraction

    def _update_liquid_volume(self, dosing_event: structs.DosingEvent) -> None:
        self.liquid_volume = LiquidVolumeCalculator.update(dosing_event, self.liquid_volume, self.max_volume)

        # add to cache
        with local_persistent_storage("liquid_volume") as cache:
            cache[self.experiment] = self.liquid_volume

        if self.liquid_volume >= self.MAX_VIAL_VOLUME_TO_WARN:
            self.logger.warning(
                f"Vial is calculated to have a volume of {self.liquid_volume:.2f} mL. Is this expected?"
            )
        elif self.liquid_volume >= self.MAX_VIAL_VOLUME_TO_STOP:
            pass
            # TODO: this should publish to pumps to stop them.
            # but it is checked elsewhere

    def _update_throughput(self, dosing_event: structs.DosingEvent) -> None:
        (
            self.media_throughput,
            self.alt_media_throughput,
        ) = ThroughputCalculator.update(dosing_event, self.media_throughput, self.alt_media_throughput)

        # add to cache
        with local_persistent_storage("alt_media_throughput") as cache:
            cache[self.experiment] = self.alt_media_throughput

        with local_persistent_storage("media_throughput") as cache:
            cache[self.experiment] = self.media_throughput

    def _init_alt_media_fraction(self, initial_alt_media_fraction: float | None) -> None:
        self.add_to_published_settings(
            "alt_media_fraction",
            {
                "datatype": "float",
                "settable": False,
            },
        )

        if initial_alt_media_fraction is None:
            with local_persistent_storage("alt_media_fraction") as cache:
                self.alt_media_fraction = cache.get(
                    self.experiment, config.getfloat("bioreactor", "initial_alt_media_fraction", fallback=0.0)
                )
        else:
            self.alt_media_fraction = float(initial_alt_media_fraction)

        assert 0 <= self.alt_media_fraction <= 1

        with local_persistent_storage("alt_media_fraction") as cache:
            cache[self.experiment] = self.alt_media_fraction

        return

    def _init_liquid_volume(
        self, initial_liquid_volume_ml: float | None, max_volume_ml: float | None
    ) -> None:
        self.add_to_published_settings(
            "liquid_volume",
            {
                "datatype": "float",
                "settable": False,  # modify using dosing_events, ex: pio run add_media --ml 1 --manually
                "unit": "mL",
                "persist": True,  # keep around so the UI can see it
            },
        )

        self.add_to_published_settings(
            "max_volume",
            {
                "datatype": "float",
                "settable": True,  # modify using dosing_events, ex: pio run add_media --ml 1 --manually
                "unit": "mL",
                "persist": True,  # keep around so the UI can see it
            },
        )

        if max_volume_ml is None:
            self.max_volume = config.getfloat("bioreactor", "max_volume_ml", fallback=14)
        else:
            self.max_volume = float(max_volume_ml)

        assert self.max_volume >= 0

        if initial_liquid_volume_ml is None:
            # look in database first, fallback to config
            with local_persistent_storage("liquid_volume") as cache:
                self.liquid_volume = cache.get(
                    self.experiment, config.getfloat("bioreactor", "initial_volume_ml", fallback=14)
                )
        else:
            self.liquid_volume = float(initial_liquid_volume_ml)

        assert self.liquid_volume >= 0

        with local_persistent_storage("liquid_volume") as cache:
            cache[self.experiment] = self.liquid_volume

        return

    def _init_volume_throughput(self) -> None:
        self.add_to_published_settings(
            "alt_media_throughput",
            {"datatype": "float", "settable": False, "unit": "mL", "persist": True},
        )
        self.add_to_published_settings(
            "media_throughput",
            {"datatype": "float", "settable": False, "unit": "mL", "persist": True},
        )

        with local_persistent_storage("alt_media_throughput") as cache:
            self.alt_media_throughput = cache.get(self.experiment, 0.0)

        with local_persistent_storage("media_throughput") as cache:
            self.media_throughput = cache.get(self.experiment, 0.0)

        return

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self._update_dosing_metrics,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
        )


class DosingAutomationJobContrib(DosingAutomationJob):
    automation_name: str


def start_dosing_automation(
    automation_name: str,
    duration: Optional[float] = None,
    skip_first_run: bool = False,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> DosingAutomationJob:
    from pioreactor.automations import dosing  # noqa: F401

    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)
    try:
        klass = available_dosing_automations[automation_name]
    except KeyError:
        raise KeyError(
            f"Unable to find {automation_name}. Available automations are {list( available_dosing_automations.keys())}"
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
        logger = create_logger("dosing_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


available_dosing_automations: dict[str, type[DosingAutomationJob]] = {}


@click.command(
    name="dosing_automation",
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
def click_dosing_automation(ctx, automation_name, duration, skip_first_run):
    """
    Start an Dosing automation
    """

    with start_dosing_automation(
        automation_name=automation_name,
        duration=float(duration),
        skip_first_run=bool(skip_first_run),
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    ) as da:
        da.block_until_disconnected()
