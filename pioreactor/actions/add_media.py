# -*- coding: utf-8 -*-

import time
from json import loads, dumps
from configparser import NoOptionError
from typing import Optional
import signal
import click

from pioreactor.utils import (
    pump_ml_to_duration,
    pump_duration_to_ml,
    local_persistant_storage,
    append_signal_handler,
)
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish, QOS
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_time, catchtime


def add_media(
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    continuously: bool = False,
    calibration: Optional[dict] = None,
) -> float:
    """

    Parameters
    ------------

    calibration:
        specify a calibration for the dosing. Should be a dict
        with fields "duration_", "hz_", "dc", and "bias_"

    """
    logger = create_logger("add_media")

    assert (
        (ml is not None) or (duration is not None) or continuously
    ), "either ml or duration must be set"
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"

    if calibration is None:
        with local_persistant_storage("pump_calibration") as cache:
            try:
                calibration = loads(cache["media_ml_calibration"])
            except KeyError:
                logger.error("Calibration not defined. Run pump calibration first.")
                return 0.0

    try:
        MEDIA_PIN = PWM_TO_PIN[config.getint("PWM_reverse", "media")]
    except NoOptionError:
        logger.error(f"Add `media` to `PWM` section to config_{unit}.ini.")
        return 0.0

    if ml is not None:
        assert ml >= 0, "ml should be greater than 0"
        duration = pump_ml_to_duration(ml, calibration["duration_"], calibration["bias_"])
        logger.info(f"{round(ml, 2)}mL")
    elif duration is not None:
        ml = pump_duration_to_ml(duration, calibration["duration_"], calibration["bias_"])
        logger.info(f"{round(duration, 2)}s")
    elif continuously:
        duration = 600
        ml = pump_duration_to_ml(duration, calibration["duration_"], calibration["bias_"])
        logger.info("Running pump continuously.")

    assert isinstance(ml, (float, int))
    assert isinstance(duration, (float, int))
    assert duration >= 0, "duration should be greater than 0"
    if duration == 0:
        return 0.0

    # publish this first, as downstream jobs need to know about it.
    json_output = dumps(
        {
            "volume_change": ml,
            "event": "add_media",
            "source_of_event": source_of_event,
            "timestamp": current_utc_time(),
        }
    )
    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events", json_output, qos=QOS.EXACTLY_ONCE
    )

    try:

        pwm = PWM(MEDIA_PIN, calibration["hz"])
        pwm.lock()

        with catchtime() as delta_time:
            pwm.start(calibration["dc"])

        time.sleep(max(0, duration - delta_time()))

        if continuously:
            while True:
                publish(
                    f"pioreactor/{unit}/{experiment}/dosing_events",
                    json_output,
                    qos=QOS.EXACTLY_ONCE,
                )
                time.sleep(duration)
    except SystemExit:
        pass
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.error(e)
    finally:
        pwm.stop()
        pwm.cleanup()
        if continuously:
            logger.info("Stopping pump.")
    return ml


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
def click_add_media(ml, duration, continuously, source_of_event):
    """
    Add media to unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    def raise_error(*args):
        raise SystemExit()

    append_signal_handler(signal.SIGTERM, raise_error)

    return add_media(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
    )
