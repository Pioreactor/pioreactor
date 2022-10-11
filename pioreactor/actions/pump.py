# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from configparser import NoOptionError
from typing import Optional

import click
from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import utils
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.pubsub import publish
from pioreactor.pubsub import QOS
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name

__all__ = ["add_media", "remove_waste", "add_alt_media"]


def _pump(
    pump_type: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.AnyPumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt
) -> float:
    """

    Parameters
    ------------
    unit: str
    experiment: str
    pump_type: one of "media", "alt_media", "waste"
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

    experiment = experiment or get_latest_experiment_name()
    unit = unit or get_unit_name()

    if pump_type == "media":
        action_name = "add_media"
    elif pump_type == "alt_media":
        action_name = "add_alt_media"
    elif pump_type == "waste":
        action_name = "remove_waste"
    else:
        raise ValueError(f"{pump_type} not valid.")

    logger = create_logger(action_name, experiment=experiment, unit=unit)

    assert (
        (ml is not None) or (duration is not None) or continuously
    ), "either ml or duration must be set"
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"

    with utils.publish_ready_to_disconnected_state(unit, experiment, action_name) as state:

        if calibration is None:
            with utils.local_persistant_storage("current_pump_calibration") as cache:
                try:
                    calibration = decode(cache[pump_type], type=structs.AnyPumpCalibration)
                except KeyError:
                    if continuously:
                        calibration = structs.PumpCalibration(
                            name="cont",
                            timestamp=current_utc_datetime(),
                            pump=pump_type,
                            duration_=1.0,
                            hz=200.0,
                            dc=100.0,
                            bias_=0,
                            voltage=-1,
                        )
                    else:
                        logger.error(
                            f"Calibration not defined. Run {pump_type} pump calibration first."
                        )
                        raise exc.CalibrationError(
                            f"Calibration not defined. Run {pump_type} pump calibration first."
                        )

        assert calibration is not None
        try:
            GPIO_PIN = PWM_TO_PIN[config.get("PWM_reverse", pump_type)]
        except NoOptionError:
            logger.error(f"Add `{pump_type}` to `PWM` section to config_{unit}.ini.")
            return 0.0

        if ml is not None:
            ml = float(ml)
            assert ml >= 0, "ml should be greater than 0"
            duration = utils.pump_ml_to_duration(ml, calibration.duration_, calibration.bias_)
            logger.info(f"{round(ml, 2)}mL")
        elif duration is not None:
            duration = float(duration)
            ml = utils.pump_duration_to_ml(duration, calibration.duration_, calibration.bias_)
            logger.info(f"{round(duration, 2)}s")
        elif continuously:
            duration = 60.0
            ml = utils.pump_duration_to_ml(duration, calibration.duration_, calibration.bias_)
            logger.info("Running pump continuously.")

        assert isinstance(ml, float)
        assert isinstance(duration, float)

        assert duration >= 0, "duration should be greater than 0"
        if duration == 0:
            return 0.0

        # publish this first, as downstream jobs need to know about it.
        json_output = encode(
            structs.DosingEvent(
                volume_change=ml,
                event=action_name,
                source_of_event=source_of_event,
                timestamp=current_utc_datetime(),
            )
        )
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            json_output,
            qos=QOS.EXACTLY_ONCE,
        )

        try:
            pwm = PWM(GPIO_PIN, calibration.hz, experiment=experiment, unit=unit)
            pwm.lock()
        except exc.PWMError:
            return 0.0

        try:
            with catchtime() as delta_time:
                pwm.start(calibration.dc)
                pump_start_time = time.monotonic()

            state.exit_event.wait(max(0, duration - delta_time()))

            if continuously:
                while not state.exit_event.wait(duration):
                    publish(
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        json_output,
                        qos=QOS.EXACTLY_ONCE,
                    )

        except SystemExit:
            # a SigInt, SigKill occurred
            pass
        except Exception as e:
            # some other unexpected error
            logger.debug(e, exc_info=True)
            logger.error(e)
        finally:
            pwm.stop()
            pwm.cleanup()

            if continuously:
                logger.info(f"Stopping {pump_type} pump.")

            if state.exit_event.is_set():
                # ended early for some reason
                shortened_duration = time.monotonic() - pump_start_time
                ml = utils.pump_duration_to_ml(
                    shortened_duration, calibration.duration_, calibration.bias_
                )

        return ml


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
    return _pump(
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
    return _pump(
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
    return _pump(
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
