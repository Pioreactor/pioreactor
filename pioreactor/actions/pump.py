# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from configparser import NoOptionError
from functools import partial
from threading import Event
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
from pioreactor.logging import CustomLogger
from pioreactor.pubsub import Client
from pioreactor.pubsub import QOS
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name

DEFAULT_PWM_CALIBRATION = structs.PumpCalibration(
    # TODO: provide better estimates for duration_ and bias_ based on some historical data.
    # it can even be a function of voltage
    name="default",
    pioreactor_unit=get_unit_name(),
    created_at=default_datetime_for_pioreactor(),
    pump="",
    hz=200.0,
    dc=100.0,
    duration_=1.0,
    bias_=0,
    voltage=-1,
)


# Initialize the thread pool with a worker threads.
# a pool is needed to avoid eventual memory overflow when multiple threads are created and allocated over time.
_thread_pool = ThreadPoolExecutor(max_workers=3)  # one for each pump


class PWMPump:
    def __init__(
        self,
        unit: str,
        experiment: str,
        pin: pt.GpioPin,
        calibration: Optional[structs.AnyPumpCalibration] = None,
        mqtt_client: Optional[Client] = None,
        logger: Optional[CustomLogger] = None,
    ) -> None:
        self.pin = pin
        self.calibration = calibration
        self.interrupt = Event()

        self.pwm = PWM(
            self.pin,
            (self.calibration or DEFAULT_PWM_CALIBRATION).hz,
            experiment=experiment,
            unit=unit,
            pubsub_client=mqtt_client,
            logger=logger,
        )

        self.pwm.lock()

    def clean_up(self) -> None:
        self.pwm.clean_up()
        # self._thread_pool.shutdown(wait=False)  # Shutdown the thread pool

    def continuously(self, block: bool = True) -> None:
        calibration = self.calibration or DEFAULT_PWM_CALIBRATION
        self.interrupt.clear()

        if block:
            self.pwm.start(calibration.dc)
            self.interrupt.wait()
            self.stop()
        else:
            self.pwm.start(calibration.dc)

    def stop(self) -> None:
        self.pwm.stop()
        self.interrupt.set()

    def by_volume(self, ml: pt.mL, block: bool = True) -> None:
        if ml < 0:
            raise ValueError("ml >= 0")

        self.interrupt.clear()

        if ml == 0:
            return

        if self.calibration is None:
            raise exc.CalibrationError(
                "Calibration not defined. Run pump calibration first to use volume-based dosing."
            )

        seconds = self.ml_to_durations(ml)
        return self.by_duration(seconds, block=block)

    def by_duration(self, seconds: pt.Seconds, block: bool = True) -> None:
        if seconds < 0:
            raise ValueError("seconds >= 0")

        self.interrupt.clear()

        if seconds == 0:
            return

        calibration = self.calibration or DEFAULT_PWM_CALIBRATION
        if block:
            self.pwm.start(calibration.dc)
            self.interrupt.wait(seconds)
            self.stop()
        else:
            _thread_pool.submit(self.by_duration, seconds, True)
            return

    def duration_to_ml(self, seconds: pt.Seconds) -> pt.mL:
        if self.calibration is None:
            raise exc.CalibrationError("Calibration not defined. Run pump calibration first.")

        return self.calibration.duration_to_ml(seconds)

    def ml_to_durations(self, ml: pt.mL) -> pt.Seconds:
        if self.calibration is None:
            raise exc.CalibrationError("Calibration not defined. Run pump calibration first.")

        return self.calibration.ml_to_duration(ml)

    def __enter__(self) -> PWMPump:
        return self

    def __exit__(self, *args) -> None:
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


def _get_pin(pump_type: str, config) -> pt.GpioPin:
    return PWM_TO_PIN[config.get("PWM_reverse", pump_type)]


def _get_calibration(pump_type: str) -> structs.AnyPumpCalibration:
    # TODO: make sure current voltage is the same as calibrated. Actually where should that check occur? in Pump?
    with utils.local_persistant_storage("current_pump_calibration") as cache:
        try:
            return decode(cache[pump_type], type=structs.AnyPumpCalibration)  # type: ignore
        except KeyError:
            raise exc.CalibrationError(f"Calibration not defined. Run {pump_type} pump calibration first.")


def _publish_pump_action(
    pump_action: str,
    ml: pt.mL,
    unit: str,
    experiment: str,
    mqtt_client: Client,
    source_of_event: Optional[str] = None,
) -> structs.DosingEvent:
    dosing_event = structs.DosingEvent(
        volume_change=ml,
        event=pump_action,
        source_of_event=source_of_event,
        timestamp=current_utc_datetime(),
    )

    mqtt_client.publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        encode(dosing_event),
        qos=QOS.EXACTLY_ONCE,
    )
    return dosing_event


def _to_human_readable_action(ml: Optional[float], duration: Optional[float], pump_type: str) -> str:
    if pump_type == "waste":
        if duration is not None:
            return f"Removing waste for {round(duration,2)}s."
        elif ml is not None:
            return f"Removing {round(ml,3)} mL waste."
        else:
            raise ValueError()
    elif pump_type == "media":
        if duration is not None:
            return f"Adding media for {round(duration,2)}s."
        elif ml is not None:
            return f"Adding {round(ml,3)} mL media."
        else:
            raise ValueError()
    elif pump_type == "alt_media":
        if duration is not None:
            return f"Adding alt-media for {round(duration,2)}s."
        elif ml is not None:
            return f"Adding {round(ml,3)} mL alt-media."
        else:
            raise ValueError()
    else:
        raise ValueError()


def _pump_action(
    pump_type: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ml: Optional[pt.mL] = None,
    duration: Optional[pt.Seconds] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.AnyPumpCalibration] = None,
    continuously: bool = False,
    config=config,  # techdebt, don't use
    manually: bool = False,
    mqtt_client: Optional[Client] = None,
    logger: Optional[CustomLogger] = None,
    job_source: Optional[str] = None,
) -> pt.mL:
    """
    Returns the mL cycled. However,
    If calibration is not defined or available on disk, returns gibberish.
    """
    if not ((ml is not None) or (duration is not None) or continuously):
        raise ValueError("either ml or duration must be set")
    if (ml is not None) and (duration is not None):
        raise ValueError("Only select ml or duration")

    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)

    action_name = _get_pump_action(pump_type)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    try:
        pin = _get_pin(pump_type, config)
    except NoOptionError:
        logger.error(f"Config entry not found. Add `{pump_type}` to `PWM` section to config_{unit}.ini.")
        return 0.0

    if calibration is None:
        try:
            calibration = _get_calibration(pump_type)
        except exc.CalibrationError:
            pass

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

        with PWMPump(
            unit, experiment, pin, calibration=calibration, mqtt_client=mqtt_client, logger=logger
        ) as pump:
            if manually:
                assert ml is not None
                ml = float(ml)
                if ml < 0:
                    raise ValueError("ml should be greater than or equal to 0")
                duration = 0.0
                logger.info(f"{_to_human_readable_action(ml, None, pump_type)} (exchanged manually)")
            elif ml is not None:
                ml = float(ml)
                if calibration is None:
                    logger.error(f"Calibration not defined. Run {pump_type} pump calibration first.")
                    raise exc.CalibrationError(
                        f"Calibration not defined. Run {pump_type} pump calibration first."
                    )

                if ml < 0:
                    raise ValueError("ml should be greater than or equal to 0")
                duration = pump.ml_to_durations(ml)
                logger.info(_to_human_readable_action(ml, None, pump_type))
            elif duration is not None:
                duration = float(duration)
                try:
                    ml = pump.duration_to_ml(duration)  # can be wrong if calibration is not defined
                except exc.CalibrationError:
                    ml = DEFAULT_PWM_CALIBRATION.duration_to_ml(duration)  # naive
                logger.info(_to_human_readable_action(None, duration, pump_type))
            elif continuously:
                duration = 2.5
                try:
                    ml = pump.duration_to_ml(duration)  # can be wrong if calibration is not defined
                except exc.CalibrationError:
                    ml = DEFAULT_PWM_CALIBRATION.duration_to_ml(duration)
                logger.info(f"Running {pump_type} pump continuously.")

            assert duration is not None
            assert ml is not None
            duration = float(duration)
            ml = float(ml)
            assert isinstance(ml, pt.mL)
            assert isinstance(duration, pt.Seconds)

            # publish this first, as downstream jobs need to know about it.
            dosing_event = _publish_pump_action(
                action_name, ml, unit, experiment, mqtt_client, source_of_event
            )

            pump_start_time = time.monotonic()

            if manually:
                return 0.0
            elif not continuously:
                pump.by_duration(duration, block=False)
                # how does this work? What's up with the (or True)?
                # exit_event.wait returns True iff the event is set, i.e by an interrupt. If we timeout (good path)
                # then we eval (False or True), hence we break out of this while loop.
                while not (state.exit_event.wait(duration) or True):
                    pump.interrupt.set()
            else:
                pump.continuously(block=False)

                # we only break out of this while loop via a interrupt or MQTT signal => event.set()
                while not state.exit_event.wait(duration):
                    # republish information
                    dosing_event = replace(dosing_event, timestamp=current_utc_datetime())
                    mqtt_client.publish(
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        encode(dosing_event),
                        qos=QOS.AT_MOST_ONCE,  # we don't need the same level of accuracy here
                    )
                pump.stop()
                logger.info(f"Stopped {pump_type} pump.")

        if state.exit_event.is_set():
            # ended early
            shortened_duration = time.monotonic() - pump_start_time
            return pump.duration_to_ml(shortened_duration)
        return ml


def _liquid_circulation(
    pump_type: str,
    duration: pt.Seconds,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    config=config,
    mqtt_client: Optional[Client] = None,
    logger: Optional[CustomLogger] = None,
    **kwargs,
) -> tuple[pt.mL, pt.mL]:
    """
    This function runs a continuous circulation of liquid using two pumps - one for waste and the other for the specified
    `pump_type`. The function takes in the `pump_type`, `unit` and `experiment` as arguments, where `pump_type` specifies
    the type of pump to be used for the liquid circulation.

    The `waste_pump` is run continuously first, followed by the `media_pump`, with each pump running for 2 seconds.

    :param pump_type: A string that specifies the type of pump to be used for the liquid circulation.
    :param unit: (Optional) A string that specifies the unit name. If not provided, the unit name will be obtained.
    :param experiment: (Optional) A string that specifies the experiment name. If not provided, the latest experiment name
                       will be obtained.
    :return: None
    """
    action_name = f"circulate_{pump_type}"
    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)
    duration = float(duration)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    waste_pin, media_pin = _get_pin("waste", config), _get_pin(pump_type, config)

    try:
        waste_calibration = _get_calibration("waste")
    except exc.CalibrationError:
        waste_calibration = DEFAULT_PWM_CALIBRATION

    try:
        media_calibration = _get_calibration(pump_type)
    except exc.CalibrationError:
        media_calibration = DEFAULT_PWM_CALIBRATION

    # we "pulse" the media pump so that the waste rate < media rate. By default, we pulse at a ratio of 1 waste : 0.85 media.
    # if we know the calibrations for each pump, we will use a different rate.
    ratio = 0.85

    if waste_calibration != DEFAULT_PWM_CALIBRATION and media_calibration != DEFAULT_PWM_CALIBRATION:
        # provided with calibrations, we can compute if media_rate > waste_rate, which is a danger zone!
        if media_calibration.duration_ > waste_calibration.duration_:
            ratio = min(waste_calibration.duration_ / media_calibration.duration_, ratio)
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
            with catchtime() as running_waste_duration:
                waste_pump.continuously(block=False)
                time.sleep(1)
                logger.info(f"Running {pump_type} for {duration}s.")

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

circulate_media = partial(_liquid_circulation, "media")
circulate_alt_media = partial(_liquid_circulation, "alt_media")
add_media = partial(_pump_action, "media")
remove_waste = partial(_pump_action, "waste")
add_alt_media = partial(_pump_action, "alt_media")


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
) -> float:
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
) -> float:
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
) -> float:
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
