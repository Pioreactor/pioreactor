# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from configparser import NoOptionError
from threading import Event
from threading import Thread
from typing import Optional

import click
from msgspec.json import decode
from msgspec.json import encode
from msgspec.structs import replace

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import utils
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.pubsub import QOS
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


class Pump:

    DEFAULT_CALIBRATION = structs.PumpCalibration(
        name="default",
        timestamp="2000-01-01 00:00:00",
        pump="",
        hz=200.0,  # is this an okay default?
        dc=100.0,
        duration_=1.0,
        bias_=0,
        voltage=-1,
    )

    calibration = DEFAULT_CALIBRATION

    def __init__(
        self,
        unit: str,
        experiment: str,
        pin: pt.GpioPin,
        calibration: Optional[structs.AnyPumpCalibration] = None,
        mqtt_client=None,
    ) -> None:
        self.pin = pin

        if calibration is not None:
            self.calibration = calibration

        self.interrupt = Event()

        self.pwm = PWM(
            self.pin,
            self.calibration.hz,
            experiment=experiment,
            unit=unit,
            pubsub_client=mqtt_client,
        )

        self.pwm.lock()

    def clean_up(self):
        self.pwm.cleanup()

    def continuously(self, block=True):
        if block:
            self.pwm.start(self.calibration.dc)
            self.interrupt.wait()
            self.stop()
        else:
            self.pwm.start(self.calibration.dc)

    def stop(self):
        self.pwm.stop()

    def by_volume(self, ml: float, block: bool = True) -> None:
        assert ml >= 0
        if self.calibration is None:
            raise exc.CalibrationError(
                "Calibration not defined. Run pump calibration first to use volume-based dosing."
            )

        seconds = self.to_durations(ml)
        self.by_duration(seconds, block=block)

    def by_duration(self, seconds, block=True) -> None:
        assert seconds >= 0
        if block:
            self.pwm.start(self.calibration.dc)
            self.interrupt.wait(seconds)
            self.stop()
        else:
            t = Thread(target=self.by_duration, args=(seconds, True), daemon=True)
            t.start()
            return

    def to_ml(self, seconds: float) -> float:
        if self.calibration is None:
            raise exc.CalibrationError("Calibration not defined. Run pump calibration first.")

        return utils.pump_duration_to_ml(seconds, self.calibration)

    def to_durations(self, ml: float) -> float:
        if self.calibration is None:
            raise exc.CalibrationError("Calibration not defined. Run pump calibration first.")

        return utils.pump_ml_to_duration(ml, self.calibration)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.clean_up()


def _get_pump_action(pump_type: str) -> str:
    if pump_type == "media":
        return "add_media"
    elif pump_type == "alt_media":
        return "add_alt_media"
    elif pump_type == "waste":
        return "remove_waste"
    else:
        raise ValueError(f"{pump_type} not valid.")


def _get_pin(pump_type):
    return PWM_TO_PIN[config.get("PWM_reverse", pump_type)]


def _get_calibration(pump_type: str) -> structs.AnyPumpCalibration:
    # TODO: make sure current voltage is the same as calibrated.
    with utils.local_persistant_storage("current_pump_calibration") as cache:
        try:
            return decode(cache[pump_type], type=structs.AnyPumpCalibration)  # type: ignore
        except KeyError:
            raise exc.CalibrationError(
                f"Calibration not defined. Run {pump_type} pump calibration first."
            )


def _pump_action(
    pump_type: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.AnyPumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt, don't use
) -> float:

    assert (
        (ml is not None) or (duration is not None) or continuously
    ), "either ml or duration must be set"
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"

    experiment = experiment or get_latest_experiment_name()
    unit = unit or get_unit_name()

    action_name = _get_pump_action(pump_type)
    logger = create_logger(action_name, experiment=experiment, unit=unit)

    try:
        pin = _get_pin(pump_type)
    except NoOptionError:
        logger.error(f"Add `{pump_type}` to `PWM` section to config_{unit}.ini.")
        return 0.0

    if calibration is None:
        try:
            calibration = _get_calibration(pump_type)
        except exc.CalibrationError as e:
            logger.error(f"Calibration not defined. Run {pump_type} pump calibration first.")
            raise e

    with utils.publish_ready_to_disconnected_state(unit, experiment, action_name) as state:

        client = state.client

        with Pump(unit, experiment, pin, calibration=calibration, mqtt_client=client) as pump:

            if ml is not None:
                ml = float(ml)
                assert ml >= 0, "ml should be greater than or equal to 0"
                duration = pump.to_durations(ml)
                logger.info(f"{round(ml, 2)}mL")
            elif duration is not None:
                duration = float(duration)
                ml = pump.to_ml(duration)
                logger.info(f"{round(duration, 2)}s")
            elif continuously:
                duration = 10.0
                ml = pump.to_ml(duration)
                logger.info(f"Running {pump_type} pump continuously.")

            # publish this first, as downstream jobs need to know about it.
            dosing_event = structs.DosingEvent(
                volume_change=ml,
                event=action_name,
                source_of_event=source_of_event,
                timestamp=current_utc_datetime(),
            )

            client.publish(
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(dosing_event),
                qos=QOS.EXACTLY_ONCE,
            )

            pump_start_time = time.monotonic()

            if not continuously:
                pump.by_duration(ml, block=True)

            else:
                pump.continuously(block=False)
                while not state.exit_event.wait(duration):
                    # republish information
                    dosing_event = replace(dosing_event, timestamp=current_utc_datetime())
                    client.publish(
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        encode(dosing_event),
                        qos=QOS.AT_MOST_ONCE,  # we don't need the same level of accuracy here
                    )
                pump.stop()
                logger.info(f"Stopped {pump_type} pump.")

            if state.exit_event.is_set():
                # ended early
                shortened_duration = time.monotonic() - pump_start_time
                ml = pump.to_ml(shortened_duration)

        assert isinstance(ml, float)
        return ml


def cycle_media(unit=None, experiment=None) -> None:
    action_name = "cycle_media"
    experiment = experiment or get_latest_experiment_name()
    unit = unit or get_unit_name()

    waste_calibration = _get_calibration("waste")
    media_calibration = _get_calibration("media")
    waste_pin = _get_pin("waste")
    media_pin = _get_pin("media")

    logger = create_logger(action_name, experiment=experiment, unit=unit)

    with utils.publish_ready_to_disconnected_state(unit, experiment, action_name) as state:
        client = state.client

        with Pump(
            unit,
            experiment,
            pin=waste_pin,
            calibration=waste_calibration,
            mqtt_client=client,
        ) as waste_pump, Pump(
            unit,
            experiment,
            pin=media_pin,
            calibration=media_calibration,
            mqtt_client=client,
        ) as media_pump:
            logger.info("Running waste and media pump continuously.")
            waste_pump.continuously(block=False)
            time.sleep(1)
            media_pump.continuously(block=False)

            state.block_until_disconnected()

            media_pump.stop()
            time.sleep(1)
            waste_pump.stop()
            logger.info("Stopped pumps.")

    return


def add_media(
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.MediaPumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt
) -> float:
    """
    Parameters
    ------------
    unit: str
    experiment: str
    ml: float
        Amount of volume to pass, in mL
    duration: float
        Duration to run pump, in seconds
    calibration: structs.PumpCalibration
    continuously: bool
        Run pump continuously.
    source_of_event: str
        A human readable description of the source


    Returns
    -----------
    Amount of volume passed (approximate in some cases)

    """
    pump_type = "media"
    return _pump_action(
        pump_type,
        unit,
        experiment,
        ml,
        duration,
        source_of_event,
        calibration,
        continuously,
        config=config,
    )


def remove_waste(
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.WastePumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt
) -> float:
    """
    Parameters
    ------------
    unit: str
    experiment: str
    ml: float
        Amount of volume to pass, in mL
    duration: float
        Duration to run pump, in seconds
    calibration: structs.PumpCalibration
    continuously: bool
        Run pump continuously.
    source_of_event: str
        A human readable description of the source

    Returns
    -----------
    Amount of volume passed (approximate in some cases)

    """
    pump_type = "waste"
    return _pump_action(
        pump_type,
        unit,
        experiment,
        ml,
        duration,
        source_of_event,
        calibration,
        continuously,
        config=config,
    )


def add_alt_media(
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.AltMediaPumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt
) -> float:
    """
    Parameters
    ------------
    unit: str
    experiment: str
    ml: float
        Amount of volume to pass, in mL
    duration: float
        Duration to run pump, in seconds
    calibration: structs.PumpCalibration
    continuously: bool
        Run pump continuously.
    source_of_event: str
        A human readable description of the source


    Returns
    -----------
    Amount of volume passed (approximate in some cases)

    """
    pump_type = "alt_media"
    return _pump_action(
        pump_type,
        unit,
        experiment,
        ml,
        duration,
        source_of_event,
        calibration,
        continuously,
        config=config,
    )


@click.command(name="add_alt_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--dry-run", is_flag=True, help="don't run the PWMs")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_alt_media(
    ml: Optional[float],
    duration: Optional[float],
    continuously: bool,
    source_of_event: Optional[str],
):
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return add_alt_media(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
    )


@click.command(name="remove_waste")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--dry-run", is_flag=True, help="don't run the PWMs")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - for logging",
)
def click_remove_waste(
    ml: Optional[float],
    duration: Optional[float],
    continuously: bool,
    source_of_event: Optional[str],
):
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return remove_waste(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
    )


@click.command(name="add_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--dry-run", is_flag=True, help="don't run the PWMs")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_media(
    ml: Optional[float],
    duration: Optional[float],
    continuously: bool,
    source_of_event: Optional[str],
):
    """
    Add media to unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return add_media(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
    )
