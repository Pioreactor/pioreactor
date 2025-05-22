# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from configparser import NoOptionError
from functools import partial
from threading import Event
from typing import cast
from typing import Optional

import click
from msgspec.json import encode
from msgspec.structs import replace

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import utils
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.pubsub import Client
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name


def get_default_calibration() -> structs.SimplePeristalticPumpCalibration:
    return structs.SimplePeristalticPumpCalibration(
        calibration_name="__default_pump_calibration",
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=default_datetime_for_pioreactor(),
        hz=250.0,
        dc=95.0,
        voltage=-1,
        curve_type="poly",
        curve_data_=[0.0911, 0.0],  # 0.0911 is a pretty okay estimate for the slope
        recorded_data={"x": [], "y": []},
    )


def is_default_calibration(cal: structs.SimplePeristalticPumpCalibration):
    return cal.calibration_name == "__default_pump_calibration"


# Initialize the thread pool with a worker threads.
# a pool is needed to avoid eventual memory overflow when multiple threads are created and allocated over time.
_thread_pool = ThreadPoolExecutor(max_workers=3)


class PWMPump:
    def __init__(
        self,
        unit: str,
        experiment: str,
        pin: pt.GpioPin,
        calibration: structs.SimplePeristalticPumpCalibration,
        mqtt_client: Optional[Client] = None,
        logger: Optional[CustomLogger] = None,
    ) -> None:
        if calibration is None:
            raise ValueError("Calibration must be provided to PWMPump.")
        self.pin = pin
        self.calibration = calibration
        self.interrupt = Event()

        self.pwm = PWM(
            self.pin,
            self.calibration.hz,
            experiment=experiment,
            unit=unit,
            pub_client=mqtt_client,
            logger=logger,
        )
        self.pwm.lock()

    def clean_up(self) -> None:
        self.pwm.clean_up()

    def start(self, duty_cycle: float) -> None:
        self.interrupt.clear()
        self.pwm.start(duty_cycle)

    def continuously(self, block: bool = True) -> None:
        if block:
            self.start(self.calibration.dc)
            self.interrupt.wait()
            self.stop()
        else:
            self.start(self.calibration.dc)

    def stop(self) -> None:
        self.pwm.stop()
        self.interrupt.set()

    def by_volume(self, ml: pt.mL, block: bool = True) -> None:
        if ml < 0:
            raise ValueError("ml must be greater than or equal to 0")
        if ml == 0:
            self.stop()
            return
        seconds = self.ml_to_duration(ml)
        self.by_duration(seconds, block=block)

    def by_duration(self, seconds: pt.Seconds, block: bool = True) -> None:
        if seconds < 0:
            raise ValueError("seconds must be >= 0")
        if seconds == 0:
            self.stop()  # need to set the interrupt!
            return
        if block:
            self.start(self.calibration.dc)
            self.interrupt.wait(seconds)
            self.stop()
        else:
            # Offload to thread pool to avoid blocking the caller
            _thread_pool.submit(self.by_duration, seconds, True)

    def duration_to_ml(self, seconds: pt.Seconds) -> pt.mL:
        return self.calibration.duration_to_ml(seconds)

    def ml_to_duration(self, ml: pt.mL) -> pt.Seconds:
        return self.calibration.ml_to_duration(ml)

    def __enter__(self) -> "PWMPump":
        return self

    def __exit__(self, *args) -> None:
        self.stop()
        self.clean_up()


def _get_pin(pump_device: PumpCalibrationDevices) -> pt.GpioPin:
    return PWM_TO_PIN[
        cast(pt.PwmChannel, config.get("PWM_reverse", pump_device.removesuffix("_pump")))
    ]  # backwards compatibility


def _get_calibration(pump_device: PumpCalibrationDevices) -> structs.SimplePeristalticPumpCalibration:
    # TODO: make sure current voltage is the same as calibrated. Actually where should that check occur? in Pump?
    cal = load_active_calibration(pump_device)
    if cal is None:
        return get_default_calibration()
    else:
        return cal


def publish_async(client, topic, payload, **kwargs):
    _thread_pool.submit(client.publish, topic, payload, **kwargs)


def _to_human_readable_action(
    ml: Optional[float], duration: Optional[float], pump_device: PumpCalibrationDevices
) -> str:
    if pump_device == "waste_pump":
        if duration is not None:
            return f"Removing waste for {round(duration,2)}s."
        elif ml is not None:
            return f"Removing {round(ml,3)} mL waste."
        else:
            raise ValueError()
    elif pump_device == "media_pump":
        if duration is not None:
            return f"Adding media for {round(duration,2)}s."
        elif ml is not None:
            return f"Adding {round(ml,3)} mL media."
        else:
            raise ValueError()
    elif pump_device == "alt_media_pump":
        if duration is not None:
            return f"Adding alt-media for {round(duration,2)}s."
        elif ml is not None:
            return f"Adding {round(ml,3)} mL alt-media."
        else:
            raise ValueError()
    else:
        raise ValueError()


def _pump_action(
    pump_device: PumpCalibrationDevices,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[pt.mL] = None,
    duration: Optional[pt.Seconds] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.SimplePeristalticPumpCalibration] = None,
    continuously: bool = False,
    manually: bool = False,
    mqtt_client: Optional[Client] = None,
    logger: Optional[CustomLogger] = None,
    job_source: Optional[str] = None,
) -> pt.mL:
    """
    Returns the mL cycled. However,
    If calibration is not defined or available on disk, returns gibberish.
    """

    def _get_pump_action(pump_device: PumpCalibrationDevices) -> str:
        if pump_device == "media_pump":
            return "add_media"
        elif pump_device == "alt_media_pump":
            return "add_alt_media"
        elif pump_device == "waste_pump":
            return "remove_waste"
        else:
            raise ValueError(f"{pump_device} not valid.")

    if not ((ml is not None) or (duration is not None) or continuously):
        raise ValueError("either ml or duration must be set")
    if (ml is not None) and (duration is not None):
        raise ValueError("Only select ml or duration")

    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)

    action_name = _get_pump_action(pump_device)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    try:
        pin = _get_pin(pump_device)
    except NoOptionError:
        logger.error(
            f"Config entry not found. Add `{pump_device.removesuffix('_pump')}` to `PWM` section to config_{unit}.ini."
        )
        return 0.0

    if calibration is None:
        try:
            calibration = _get_calibration(pump_device)
        except exc.CalibrationError as e:
            logger.error(str(e))
            raise

    assert calibration is not None

    with utils.managed_lifecycle(
        unit,
        experiment,
        action_name,
        mqtt_client=mqtt_client,
        exit_on_mqtt_disconnect=True,
        mqtt_client_kwargs={"keepalive": 10},
        job_source=job_source,
    ) as state:
        mqtt_client = state.mqtt_client

        if manually:
            assert ml is not None
            ml = float(ml)
            if ml < 0:
                raise ValueError("ml should be greater than or equal to 0")
            duration = 0.0
            logger.info(f"{_to_human_readable_action(ml, None, pump_device)} (exchanged manually)")
        elif ml is not None:
            ml = float(ml)
            if is_default_calibration(calibration):
                logger.error(
                    f"Active calibration not found. Run {pump_device} calibration first: `pio calibrations run --device {pump_device}` or set active with `pio calibrations set-active`"
                )
                raise exc.CalibrationError(
                    f"Active calibration not found. Run {pump_device} calibration: `pio calibrations run --device {pump_device}`, or set active with `pio calibrations set-active`"
                )

            if ml < 0:
                raise ValueError("ml should be greater than or equal to 0")
            duration = calibration.ml_to_duration(ml)
            logger.info(_to_human_readable_action(ml, None, pump_device))
        elif duration is not None:
            duration = float(duration)
            ml = calibration.duration_to_ml(duration)  # can be wrong if calibration is not defined

            logger.info(_to_human_readable_action(None, duration, pump_device))
        elif continuously:
            duration = 1.0
            ml = calibration.duration_to_ml(duration)  # can be wrong if calibration is not defined

            logger.info(f"Running {pump_device} continuously.")

        assert duration is not None
        assert ml is not None

        duration = pt.Seconds(duration)
        ml = pt.mL(ml)

        empty_dosing_event = structs.DosingEvent(
            volume_change=0.0,
            event=action_name,
            source_of_event=source_of_event,
            timestamp=current_utc_datetime(),
        )

        if manually:
            publish_async(
                mqtt_client,
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(replace(empty_dosing_event, volume_change=ml)),
            )
            return 0.0

        with PWMPump(
            unit, experiment, pin, calibration=calibration, mqtt_client=mqtt_client, logger=logger
        ) as pump:
            sub_duration = 0.5
            volume_moved_ml = 0.0

            pump_start_time = time.monotonic()

            if not continuously:
                pump.by_duration(duration, block=False)  # start pump

                while not pump.interrupt.is_set():
                    sub_volume_moved_ml = 0.0
                    time_left = duration - (time.monotonic() - pump_start_time)
                    if time_left <= 0:
                        # this is an edge case where the time has surpassed, but the interrupt isn't set yet.
                        pump.interrupt.wait()
                        break

                    elif time_left >= sub_duration:
                        sub_volume_moved_ml = pump.duration_to_ml(sub_duration)

                    elif sub_duration > time_left:
                        # last remaining bit.
                        sub_volume_moved_ml = ml - volume_moved_ml

                    dosing_event = replace(
                        empty_dosing_event,
                        timestamp=current_utc_datetime(),
                        volume_change=sub_volume_moved_ml,
                    )
                    volume_moved_ml += sub_volume_moved_ml

                    publish_async(
                        mqtt_client,
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        encode(dosing_event),
                    )

                    if state.exit_event.wait(min(sub_duration, time_left)):
                        pump.interrupt.set()
                        pump_stop_time = time.monotonic()

                        # ended early. We should calculate how much _wasnt_ added, and update that.
                        actual_volume_moved_ml = pump.duration_to_ml(pump_stop_time - pump_start_time)
                        correction_factor = (
                            actual_volume_moved_ml - volume_moved_ml
                        )  # reported too much since we log first before dosing

                        dosing_event = replace(
                            empty_dosing_event,
                            timestamp=current_utc_datetime(),
                            volume_change=correction_factor,
                        )
                        publish_async(
                            mqtt_client,
                            f"pioreactor/{unit}/{experiment}/dosing_events",
                            encode(dosing_event),
                        )

                        logger.info(f"Stopped {pump_device} early.")
                        return actual_volume_moved_ml

                return volume_moved_ml

            else:
                pump.continuously(block=False)  # start pump

                while True:
                    sub_volume_moved_ml = pump.duration_to_ml(sub_duration)

                    dosing_event = replace(
                        empty_dosing_event,
                        timestamp=current_utc_datetime(),
                        volume_change=sub_volume_moved_ml,
                    )
                    volume_moved_ml += sub_volume_moved_ml

                    publish_async(
                        mqtt_client,
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        encode(dosing_event),
                    )

                    if state.exit_event.wait(sub_duration):
                        # this is the only way it stops?
                        pump.interrupt.set()
                        pump_stop_time = time.monotonic()

                        actual_volume_moved_ml = pump.duration_to_ml(pump_stop_time - pump_start_time)

                        correction_factor = (
                            actual_volume_moved_ml - volume_moved_ml
                        )  # reported too much since we log first before dosing

                        dosing_event = replace(
                            empty_dosing_event,
                            timestamp=current_utc_datetime(),
                            volume_change=correction_factor,
                        )
                        publish_async(
                            mqtt_client,
                            f"pioreactor/{unit}/{experiment}/dosing_events",
                            encode(dosing_event),
                        )

                        logger.info(f"Stopped {pump_device}.")
                        return actual_volume_moved_ml


def _liquid_circulation(
    pump_device: PumpCalibrationDevices,
    duration: pt.Seconds,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    mqtt_client: Optional[Client] = None,
    logger: Optional[CustomLogger] = None,
    source_of_event: Optional[str] = None,
    **kwargs,
) -> tuple[pt.mL, pt.mL]:
    """
    This function runs a continuous circulation of liquid using two pumps - one for waste and the other for the specified
    `pump_device`. The function takes in the `pump_device`, `unit` and `experiment` as arguments, where `pump_device` specifies
    the type of pump to be used for the liquid circulation.

    The `waste_pump` is run continuously first, followed by the `media_pump`, with each pump running for 2 seconds.

    :param pump_device: A string that specifies the type of pump to be used for the liquid circulation.
    :param unit: (Optional) A string that specifies the unit name. If not provided, the unit name will be obtained.
    :param experiment: (Optional) A string that specifies the experiment name. If not provided, the latest experiment name
                       will be obtained.
    :return: None
    """

    def _get_pump_action(pump_device: PumpCalibrationDevices) -> str:
        if pump_device == "media_pump":
            return "circulate_media"
        elif pump_device == "alt_media_pump":
            return "circulate_alt_media"
        else:
            raise ValueError(f"{pump_device} not valid.")

    action_name = _get_pump_action(pump_device)
    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)
    duration = float(duration)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    waste_pin, media_pin = _get_pin("waste_pump"), _get_pin(pump_device)

    waste_calibration = _get_calibration("waste_pump")
    media_calibration = _get_calibration(pump_device)

    # we "pulse" the media pump so that the waste rate < media rate. By default, we pulse at a ratio of 1 waste : 0.85 media.
    # if we know the calibrations for each pump, we will use a different rate.
    ratio = 0.85

    if not is_default_calibration(waste_calibration) and not is_default_calibration(media_calibration):
        # provided with calibrations, we can compute if media_rate > waste_rate, which is a danger zone!
        # `x_to_y(1)` asks "how much lqd is moved in 1 second"
        if media_calibration.x_to_y(1) > waste_calibration.x_to_y(1):
            ratio = min(waste_calibration.x_to_y(1) / media_calibration.x_to_y(1), ratio)
    else:
        logger.warning(
            "Calibrations don't exist for pump(s). Keep an eye on the liquid level to avoid overflowing!"
        )

    with utils.managed_lifecycle(
        unit,
        experiment,
        action_name,
        mqtt_client=mqtt_client,
        exit_on_mqtt_disconnect=True,
        mqtt_client_kwargs={"keepalive": 10},
    ) as state:
        mqtt_client = state.mqtt_client

        with PWMPump(
            unit,
            experiment,
            pin=waste_pin,
            calibration=waste_calibration,
            mqtt_client=mqtt_client,
        ) as waste_pump, PWMPump(
            unit,
            experiment,
            pin=media_pin,
            calibration=media_calibration,
            mqtt_client=mqtt_client,
        ) as media_pump:
            logger.info("Running waste continuously.")

            # assume they run it long enough such that the waste efflux position is reached.
            dosing_event = structs.DosingEvent(
                volume_change=20,
                event="remove_waste",
                source_of_event=source_of_event,
                timestamp=current_utc_datetime(),
            )
            publish_async(
                mqtt_client,
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(dosing_event),
            )

            with catchtime() as running_waste_duration:
                waste_pump.continuously(block=False)
                time.sleep(1)
                logger.info(f"Running {pump_device} for {duration}s.")

                running_duration = 0.0
                running_dosing_duration = 0.0

                while not state.exit_event.is_set() and (running_duration < duration):
                    media_pump.by_duration(min(duration, ratio), block=True)
                    state.exit_event.wait(1 - ratio)

                    running_duration += 1.0
                    running_dosing_duration += min(duration, ratio)

                time.sleep(1)
                waste_pump_duration = running_waste_duration()
                waste_pump.stop()

            logger.info("Stopped pumps.")

    return (
        media_calibration.duration_to_ml(running_dosing_duration),
        waste_calibration.duration_to_ml(waste_pump_duration),
    )


### high level functions below:

circulate_media = partial(_liquid_circulation, "media_pump")
circulate_alt_media = partial(_liquid_circulation, "alt_media_pump")
add_media = partial(_pump_action, "media_pump")
remove_waste = partial(_pump_action, "waste_pump")
add_alt_media = partial(_pump_action, "alt_media_pump")


@click.command(name="add_alt_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--manually", is_flag=True, help="The media is manually added (don't run pumps)")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_alt_media(
    ml: Optional[pt.mL],
    duration: Optional[pt.Seconds],
    continuously: bool,
    source_of_event: Optional[str],
    manually: bool,
) -> pt.mL:
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return add_alt_media(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
        manually=manually,
    )


@click.command(name="remove_waste")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--manually", is_flag=True, help="The media is manually removed (don't run pumps)")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - for logging",
)
def click_remove_waste(
    ml: Optional[pt.mL],
    duration: Optional[pt.Seconds],
    continuously: bool,
    source_of_event: Optional[str],
    manually: bool,
) -> pt.mL:
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return remove_waste(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
        manually=manually,
    )


@click.command(name="add_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--manually", is_flag=True, help="The media is manually added (don't run pumps)")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_media(
    ml: Optional[pt.mL],
    duration: Optional[pt.Seconds],
    continuously: bool,
    source_of_event: Optional[str],
    manually: bool,
) -> pt.mL:
    """
    Add media to unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return add_media(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
        manually=manually,
    )


@click.command(name="circulate_media")
@click.option("--duration", required=True, type=float)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_circulate_media(
    duration: Optional[pt.Seconds],
    source_of_event: Optional[str],
) -> tuple[pt.mL, pt.mL]:
    """
    Cycle waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return circulate_media(
        duration=duration, unit=unit, experiment=experiment, source_of_event=source_of_event
    )


@click.command(name="circulate_alt_media")
@click.option("--duration", required=True, type=float)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_circulate_alt_media(
    duration: Optional[pt.Seconds],
    source_of_event: Optional[str],
) -> tuple[pt.mL, pt.mL]:
    """
    Cycle waste/alt media from unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return circulate_alt_media(
        duration=duration, unit=unit, experiment=experiment, source_of_event=source_of_event
    )
