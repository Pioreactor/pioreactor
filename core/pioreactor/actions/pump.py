# -*- coding: utf-8 -*-
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from configparser import NoOptionError
from functools import partial
from math import isfinite
from threading import Event
from threading import RLock
from typing import Any
from typing import cast

import click
from msgspec.json import encode
from msgspec.structs import replace
from pioreactor import bioreactor
from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import utils
from pioreactor.actions.pump_execution import PumpRun
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.hardware import get_pwm_to_pin_map
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.pubsub import Client
from pioreactor.pubsub import QOS
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_pioreactor_model
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def get_default_calibration() -> structs.SimplePeristalticPumpCalibration:
    return structs.SimplePeristalticPumpCalibration(
        calibration_name="__default_pump_calibration",
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=default_datetime_for_pioreactor(),
        hz=250.0,
        dc=100.00,
        voltage=-1,
        curve_data_=structs.PolyFitCoefficients(
            coefficients=[0.0911, 0.0] if not is_testing_env() else [5.0, 0]
        ),  # go fast if in testing
        recorded_data={"x": [], "y": []},
    )


def is_default_calibration(cal: structs.SimplePeristalticPumpCalibration) -> bool:
    return cal.calibration_name == "__default_pump_calibration"


# Only hardware control uses the pool; callers own telemetry and cannot delay its deadlines.
_pump_thread_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pump-control")


class PWMPump:
    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        pin: pt.GpioPin,
        calibration: structs.SimplePeristalticPumpCalibration,
        mqtt_client: Client | None = None,
        logger: CustomLogger | None = None,
        cancel_events: tuple[Event, ...] = (),
    ) -> None:
        if calibration is None:
            raise ValueError("Calibration must be provided to PWMPump.")
        self.pin = pin
        self.calibration = calibration
        self.interrupt = Event()
        self.cancel_events = cancel_events
        self.run: PumpRun | None = None
        self._future: Future[None] | None = None
        self._operation_lock = RLock()
        self._closed = False

        self.pwm = PWM(
            self.pin,
            self.calibration.hz,
            experiment=experiment,
            unit=unit,
            pub_client=mqtt_client,
            logger=logger,
            exclusive=True,
        )

    def clean_up(self) -> None:
        with self._operation_lock:
            self._closed = True
        try:
            self.stop()
        finally:
            self.pwm.clean_up()

    @property
    def elapsed(self) -> float:
        return self.run.elapsed if self.run is not None else 0.0

    @property
    def completed(self) -> bool:
        return self.run is not None and self.run.completed

    def wait(self, timeout: float) -> bool:
        """Wait for output to stop, also cancelling queued work when its owner stops.

        Call stop() before final accounting to join the worker and surface any failure.
        """
        run = self.run
        if run is None or run.done.wait(timeout):
            return True
        if run.should_stop():
            self.stop()
            return True
        return False

    def publish_duty_cycles(self) -> None:
        self.pwm._serialize()

    def start(self, duty_cycle: float) -> None:
        future = self._begin(None, duty_cycle)
        assert self.run is not None
        while not self.run.started.wait(0.05):
            if self.run.should_stop():
                self.stop()
                return
        if future.cancelled():
            return
        try:
            if self.run.started_at is None:
                future.result()  # Surface an activation failure before returning to the caller.
            self.publish_duty_cycles()
        except BaseException:
            self.stop()
            raise

    def _begin(self, seconds: float | None, duty_cycle: float) -> Future[None]:
        with self._operation_lock:
            if self._closed:
                raise exc.PWMError("Pump is closed.")
            if self._future is not None and not self._future.done():
                raise exc.PWMError("Pump already has an active operation.")
            run = PumpRun(
                self.pwm,
                duty_cycle,
                seconds,
                self.cancel_events,
            )
            self.run = run
            self.interrupt = run.done
            self._future = _pump_thread_pool.submit(run.run)
            return self._future

    def continuously(self, block: bool = True) -> None:
        self.start(self.calibration.dc)
        if block:
            assert self._future is not None
            try:
                if not self._future.cancelled():
                    self._future.result()
            finally:
                self.stop()

    def stop(self) -> None:
        with self._operation_lock:
            run, future = self.run, self._future
            if run is not None:
                run.cancel()
            if future is not None and future.cancel():
                assert run is not None
                run.started.set()
                run.done.set()
            try:
                if future is not None and not future.cancelled():
                    future.result()
            finally:
                self.interrupt.set()
                self.pwm.stop()

    def by_volume(self, ml: pt.mL, block: bool = True) -> None:
        if not isfinite(ml) or ml < 0:
            raise ValueError("ml must be finite and greater than or equal to 0")
        self.by_duration(self.ml_to_duration(ml) if ml else 0.0, block=block)

    def by_duration(self, seconds: pt.Seconds, block: bool = True) -> Future[None] | None:
        """Run a timed dose. Nonblocking callers own telemetry until stop/cleanup."""
        if not isfinite(seconds) or seconds < 0:
            raise ValueError("seconds must be finite and >= 0")
        future = self._begin(seconds, self.calibration.dc)
        if block:
            assert self.run is not None
            while not self.run.started.wait(0.05):
                if self.run.should_stop():
                    self.stop()
                    return None
            if future.cancelled():
                return None
            try:
                self.publish_duty_cycles()
                future.result()
            finally:
                self.stop()
            return None
        return future

    def duration_to_ml(self, seconds: pt.Seconds) -> pt.mL:
        return self.calibration.duration_to_ml(seconds)

    def ml_to_duration(self, ml: pt.mL) -> pt.Seconds:
        return self.calibration.ml_to_duration(ml)

    def __enter__(self) -> "PWMPump":
        return self

    def __exit__(self, *args: object) -> None:
        self.clean_up()


def _get_pin(pump_device: PumpCalibrationDevices) -> pt.GpioPin:
    return get_pwm_to_pin_map()[
        cast(pt.PwmChannel, config.get("PWM_reverse", pump_device.removesuffix("_pump")))
    ]


def _get_calibration(pump_device: PumpCalibrationDevices) -> structs.SimplePeristalticPumpCalibration:
    cal = load_active_calibration(pump_device)
    if cal is None:
        return get_default_calibration()
    return cal


def _to_human_readable_action(
    ml: float | None, duration: float | None, pump_device: PumpCalibrationDevices
) -> str:
    if pump_device == "waste_pump":
        if duration is not None:
            return f"Removing waste for {round(duration, 2)}s."
        elif ml is not None:
            return f"Removing {round(ml, 3)} mL waste."
        else:
            raise ValueError()
    elif pump_device == "media_pump":
        if duration is not None:
            return f"Adding media for {round(duration, 2)}s."
        elif ml is not None:
            return f"Adding {round(ml, 3)} mL media."
        else:
            raise ValueError()
    elif pump_device == "alt_media_pump":
        if duration is not None:
            return f"Adding alt-media for {round(duration, 2)}s."
        elif ml is not None:
            return f"Adding {round(ml, 3)} mL alt-media."
        else:
            raise ValueError()
    else:
        raise ValueError()


def estimated_volume(
    calibration: structs.SimplePeristalticPumpCalibration,
    elapsed: float,
    *,
    completed: bool,
    requested_ml: float | None,
) -> float:
    """Cumulative estimate; apply a calibration intercept once per operation.

    A completed finite dose that actually started reports its request, including sub-tick microdoses.
    Cancelled or continuous runs use elapsed output time, never time spent queued.
    """
    if elapsed <= 0:
        return 0.0
    if completed and requested_ml is not None:
        return max(0.0, requested_ml)
    volume = max(0.0, calibration.duration_to_ml(elapsed))
    return volume if requested_ml is None else max(0.0, min(requested_ml, volume))


def _pump_action(
    pump_device: PumpCalibrationDevices,
    unit: str | None = None,
    experiment: str | None = None,
    ml: pt.mL | None = None,
    duration: pt.Seconds | None = None,
    source_of_event: str | None = None,
    calibration: structs.SimplePeristalticPumpCalibration | None = None,
    continuously: bool = False,
    mqtt_client: Client | None = None,
    logger: CustomLogger | None = None,
    job_source: str | None = None,
    cancel_event: Event | None = None,
) -> pt.mL:
    """
    Run a pump action and return the estimated mL moved.

    Continuous inflow runs while the vial has safe headroom.
    Continuous waste runs until stopped and returns its estimated volume.
    """

    # Current invariant: every pump action selects exactly one execution mode.
    if sum((ml is not None, duration is not None, continuously)) != 1:
        raise ValueError("Select exactly one of ml, duration, or continuously.")

    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)

    action_name = _get_action_name_for_pump_device(pump_device)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    continuous_inflow = continuously and pump_device in ("media_pump", "alt_media_pump")
    max_fill_volume_ml = None
    if continuous_inflow:
        max_fill_volume_ml = get_pioreactor_model().reactor_max_fill_volume_ml
        if bioreactor.get_bioreactor_value(experiment, "current_volume_ml") >= max_fill_volume_ml:
            logger.warning(
                f"Skipping continuous {pump_device} because the vial is already at the maximum safe volume."
            )
            return 0.0

    if ml is not None:
        ml = float(ml)
        if not isfinite(ml) or ml < 0:
            logger.error("ml should be greater than or equal to 0")
            raise ValueError("ml should be greater than or equal to 0")

    if duration is not None:
        duration = float(duration)
        if not isfinite(duration) or duration < 0:
            logger.error("seconds must be >= 0")
            raise ValueError("seconds must be >= 0")

    try:
        pin = _get_pin(pump_device)
    except NoOptionError as error:
        raise exc.PWMError(
            f"Config entry not found. Add `{pump_device.removesuffix('_pump')}` to `PWM` section to config_{unit}.ini."
        ) from error

    if calibration is None:
        calibration = _get_calibration(pump_device)

    if is_default_calibration(calibration):
        logger.debug(f"Using default calibration for {pump_device}.")
    else:
        logger.debug(f"Using {pump_device} calibration `{calibration.calibration_name}`.")

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

        if continuous_inflow and is_default_calibration(calibration):
            logger.error(
                f"Active calibration not found. Run {pump_device} calibration first: `pio calibrations run --device {pump_device}` or set active with `pio calibrations set-active`"
            )
            raise exc.CalibrationError(
                f"Active calibration not found. Run {pump_device} calibration: `pio calibrations run --device {pump_device}`, or set active with `pio calibrations set-active`"
            )

        if ml is not None:
            if is_default_calibration(calibration):
                logger.error(
                    f"Active calibration not found. Run {pump_device} calibration first: `pio calibrations run --device {pump_device}` or set active with `pio calibrations set-active`"
                )
                raise exc.CalibrationError(
                    f"Active calibration not found. Run {pump_device} calibration: `pio calibrations run --device {pump_device}`, or set active with `pio calibrations set-active`"
                )

            duration = calibration.ml_to_duration(ml)
            logger.info(_to_human_readable_action(ml, None, pump_device))
        elif duration is not None:
            ml = calibration.duration_to_ml(duration)  # can be wrong if calibration is not defined

            logger.info(_to_human_readable_action(None, duration, pump_device))
        elif continuously:
            logger.info(f"Running {pump_device} continuously.")

        try:
            pump_instance = PWMPump(
                unit,
                experiment,
                pin,
                calibration=calibration,
                mqtt_client=mqtt_client,
                logger=logger,
                cancel_events=(state.exit_event,) + ((cancel_event,) if cancel_event is not None else ()),
            )
        except exc.PWMLockedError as error:
            raise exc.PWMLockedError(f"Cannot run {pump_device}: {error}") from error

        with pump_instance as pump:
            empty_dosing_event = structs.DosingEvent(
                volume_change=0.0,
                event=action_name,
                source_of_event=source_of_event,
                timestamp=current_utc_datetime(),
            )

            # One cumulative estimate serves progress events and the returned volume.
            # Events report elapsed execution, not a predicted dose before it happens.
            reported_ml = 0.0

            def report_volume(volume: float) -> None:
                nonlocal reported_ml
                delta = volume - reported_ml
                if delta == 0:
                    return
                mqtt_client.publish(
                    f"pioreactor/{unit}/{experiment}/dosing_events",
                    encode(
                        replace(empty_dosing_event, timestamp=current_utc_datetime(), volume_change=delta)
                    ),
                    qos=QOS.EXACTLY_ONCE,
                )
                reported_ml = volume

            if continuously:
                # Bound inflow by the available headroom even if reporting stalls.
                if max_fill_volume_ml is not None:
                    headroom = max(
                        0.0,
                        max_fill_volume_ml - bioreactor.get_bioreactor_value(experiment, "current_volume_ml"),
                    )
                    pump.by_duration(
                        max(0.0, calibration.ml_to_duration(headroom)) if headroom else 0.0, block=False
                    )
                else:
                    pump.start(calibration.dc)
            else:
                assert duration is not None
                pump.by_duration(duration, block=False)

            next_report_at = 0.0
            while not pump.wait(0.05):
                if (
                    max_fill_volume_ml is not None
                    and bioreactor.get_bioreactor_value(experiment, "current_volume_ml") >= max_fill_volume_ml
                ):
                    pump.stop()
                    break
                if pump.elapsed > 0 and pump.elapsed >= next_report_at:
                    pump.publish_duty_cycles()
                    report_volume(
                        estimated_volume(calibration, pump.elapsed, completed=False, requested_ml=ml)
                    )
                    next_report_at = pump.elapsed + 0.5

            pump.stop()  # Surfaces worker failures, and completes hardware stop before final accounting.
            moved_ml = estimated_volume(calibration, pump.elapsed, completed=pump.completed, requested_ml=ml)
            report_volume(moved_ml)
            if continuously or not pump.completed:
                logger.info(f"Stopped {pump_device}{' early' if not continuously else ''}.")
            return moved_ml


def _liquid_circulation(
    pump_device: PumpCalibrationDevices,
    duration: pt.Seconds,
    unit: str | None = None,
    experiment: str | None = None,
    mqtt_client: Client | None = None,
    logger: CustomLogger | None = None,
    source_of_event: str | None = None,
    **kwargs: Any,
) -> tuple[pt.mL, pt.mL]:
    """
    This function runs a continuous circulation of liquid using two pumps - one for waste and the other for the specified
    `pump_device`. The function takes in the `pump_device`, `unit` and `experiment` as arguments, where `pump_device` specifies
    the type of pump to be used for the liquid circulation.

    The `waste_pump` is run continuously first, followed by periodic pulses from the media pump.

    :param pump_device: A string that specifies the type of pump to be used for the liquid circulation.
    :param unit: (Optional) A string that specifies the unit name. If not provided, the unit name will be obtained.
    :param experiment: (Optional) A string that specifies the experiment name. If not provided, the latest experiment name
                       will be obtained.
    :return: The media and waste volumes moved, in mL.
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
    if not isfinite(duration) or duration < 0:
        raise ValueError("duration must be finite and >= 0")
    if duration == 0:
        return (0.0, 0.0)

    if logger is None:
        logger = create_logger(action_name, experiment=experiment, unit=unit)

    waste_pin, media_pin = _get_pin("waste_pump"), _get_pin(pump_device)

    waste_calibration = _get_calibration("waste_pump")
    media_calibration = _get_calibration(pump_device)

    if is_default_calibration(media_calibration):
        logger.debug(f"Using default calibration for {pump_device}.")
    else:
        logger.debug(f"Using {pump_device} calibration `{media_calibration.calibration_name}`.")

    if is_default_calibration(waste_calibration):
        logger.debug("Using default calibration for waste_pump.")
    else:
        logger.debug(f"Using waste_pump calibration `{waste_calibration.calibration_name}`.")

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
            cancel_events=(state.exit_event,),
        ) as waste_pump, PWMPump(
            unit,
            experiment,
            pin=media_pin,
            calibration=media_calibration,
            mqtt_client=mqtt_client,
            cancel_events=(state.exit_event,),
        ) as media_pump:
            logger.info("Running waste continuously.")

            # Current invariant: circulation waste drains to the efflux-tube
            # level, not below it.
            dosing_event = structs.DosingEvent(
                volume_change=20,
                event="remove_waste",
                source_of_event=source_of_event,
                timestamp=current_utc_datetime(),
            )
            mqtt_client.publish(
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(dosing_event),
                qos=QOS.EXACTLY_ONCE,
            )

            waste_pump.continuously(block=False)
            state.exit_event.wait(1)
            logger.info(f"Running {pump_device} for {duration}s.")

            running_duration = 0.0
            running_dosing_duration = 0.0
            while not state.exit_event.is_set() and running_duration < duration:
                remaining_dosing_duration = duration - running_dosing_duration
                media_dosing_duration = min(remaining_dosing_duration, ratio)
                media_pump.by_duration(media_dosing_duration, block=True)
                running_dosing_duration += (
                    media_dosing_duration
                    if media_pump.completed
                    else min(media_dosing_duration, media_pump.elapsed)
                )
                state.exit_event.wait(1 - ratio)
                running_duration += 1.0

            state.exit_event.wait(1)
            waste_pump.stop()
            waste_pump_duration = waste_pump.elapsed
            logger.info("Stopped pumps.")

    return (
        media_calibration.duration_to_ml(running_dosing_duration) if running_dosing_duration else 0.0,
        waste_calibration.duration_to_ml(waste_pump_duration) if waste_pump_duration else 0.0,
    )


def _get_action_name_for_pump_device(pump_device: PumpCalibrationDevices) -> str:
    if pump_device == "media_pump":
        return "add_media"
    if pump_device == "alt_media_pump":
        return "add_alt_media"
    if pump_device == "waste_pump":
        return "remove_waste"
    raise ValueError(f"{pump_device} not valid.")


### high level functions below:

circulate_media = partial(_liquid_circulation, "media_pump")
circulate_alt_media = partial(_liquid_circulation, "alt_media_pump")
add_media = partial(_pump_action, "media_pump")
remove_waste = partial(_pump_action, "waste_pump")
add_alt_media = partial(_pump_action, "alt_media_pump")


@click.command(name="add_alt_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="add until the maximum safe volume is reached.")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_alt_media(
    ml: pt.mL | None,
    duration: pt.Seconds | None,
    continuously: bool,
    source_of_event: str | None,
) -> pt.mL:
    """
    Add alt-media from unit
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
    ml: pt.mL | None,
    duration: pt.Seconds | None,
    continuously: bool,
    source_of_event: str | None,
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
    )


@click.command(name="add_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="add until the maximum safe volume is reached.")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_media(
    ml: pt.mL | None,
    duration: pt.Seconds | None,
    continuously: bool,
    source_of_event: str | None,
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
    duration: pt.Seconds,
    source_of_event: str | None,
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
    duration: pt.Seconds,
    source_of_event: str | None,
) -> tuple[pt.mL, pt.mL]:
    """
    Cycle waste/alt media from unit
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    return circulate_alt_media(
        duration=duration, unit=unit, experiment=experiment, source_of_event=source_of_event
    )
