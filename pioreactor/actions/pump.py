# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from configparser import NoOptionError
from typing import Optional

import msgspec

from pioreactor import structs
from pioreactor import utils
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.pubsub import publish
from pioreactor.pubsub import QOS
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_time


def pump(
    unit: str,
    experiment: str,
    pump_name: str,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[structs.PumpCalibration] = None,
    continuously: bool = False,
) -> float:
    """

    Parameters
    ------------
    unit: str
    experiment: str
    pump_name: one of "media", "alt_media", "waste"
    ml: float
        Amount of volume to pass, in mL
    duration: float
        Duration to run pump, in s
    calibration:
        specify a calibration for the dosing. Should be a dict
        with fields "duration_", "hz", "dc", and "bias_"
    continuously: bool
        Run pump continuously.
    source_of_event: str
        A human readable description of the source


    Returns
    -----------
    Amount of volume passed (approximate in some cases)

    """
    action_name = {
        "media": "add_media",
        "alt_media": "add_alt_media",
        "waste": "remove_waste",
    }[pump_name]
    logger = create_logger(action_name, experiment=experiment, unit=unit)
    with utils.publish_ready_to_disconnected_state(
        unit, experiment, action_name
    ) as state:
        assert (
            (ml is not None) or (duration is not None) or continuously
        ), "either ml or duration must be set"
        assert not (
            (ml is not None) and (duration is not None)
        ), "Only select ml or duration"

        if calibration is None:
            with utils.local_persistant_storage("pump_calibration") as cache:
                try:
                    calibration = msgspec.json.decode(
                        cache[f"{pump_name}_ml_calibration"], type=structs.PumpCalibration
                    )
                except KeyError:
                    logger.error("Calibration not defined. Run pump calibration first.")
                    return 0.0

        try:
            GPIO_PIN = PWM_TO_PIN[config.get("PWM_reverse", pump_name)]
        except NoOptionError:
            logger.error(f"Add `{pump_name}` to `PWM` section to config_{unit}.ini.")
            return 0.0

        if ml is not None:
            ml = float(ml)
            assert ml >= 0, "ml should be greater than 0"
            duration = utils.pump_ml_to_duration(
                ml, calibration.duration_, calibration.bias_
            )
            logger.info(f"{round(ml, 2)}mL")
        elif duration is not None:
            duration = float(duration)
            ml = utils.pump_duration_to_ml(
                duration, calibration.duration_, calibration.bias_
            )
            logger.info(f"{round(duration, 2)}s")
        elif continuously:
            duration = 600.0
            ml = utils.pump_duration_to_ml(
                duration, calibration.duration_, calibration.bias_
            )
            logger.info("Running pump continuously.")

        assert isinstance(ml, float)
        assert isinstance(duration, float)

        assert duration >= 0, "duration should be greater than 0"
        if duration == 0:
            return 0.0

        # publish this first, as downstream jobs need to know about it.
        json_output = msgspec.json.encode(
            structs.DosingEvent(
                volume_change=ml,
                event=action_name,
                source_of_event=source_of_event,
                timestamp=current_utc_time(),
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
                logger.info(f"Stopping {pump_name} pump.")

            if state.exit_event.is_set():
                # ended early for some reason
                shortened_duration = time.monotonic() - pump_start_time
                ml = utils.pump_duration_to_ml(
                    shortened_duration, calibration.duration_, calibration.bias_
                )
        return ml
