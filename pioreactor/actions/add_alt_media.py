# -*- coding: utf-8 -*-
import time
from json import loads, dumps
from configparser import NoOptionError
from typing import Optional
import click

from pioreactor.utils import pump_ml_to_duration, pump_duration_to_ml
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish, QOS
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_time, catchtime
from pioreactor.utils import local_persistant_storage


def add_alt_media(
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    calibration: Optional[dict] = None,
) -> float:
    logger = create_logger("add_alt_media")

    # TODO: turn these into proper exceptions and logging
    assert (ml is not None) or (duration is not None), "either ml or duration must be set"
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"

    if calibration is None:
        try:
            with local_persistant_storage("pump_calibration") as cache:
                calibration = loads(cache["alt_media_ml_calibration"])
        except KeyError:
            logger.error("Calibration not defined. Run pump calibration first.")
            return 0.0

    try:
        ALT_MEDIA_PIN = PWM_TO_PIN[config.getint("PWM_reverse", "alt_media")]
    except NoOptionError:
        logger.error(f"Add `alt_media` to `PWM` section to config_{unit}.ini.")
        return 0

    if ml is not None:
        user_submitted_ml = True
        assert ml >= 0, "ml should be >= than 0"
        duration = pump_ml_to_duration(
            ml,
            calibration["duration_"],
            calibration["bias_"],
        )
    elif duration is not None:
        user_submitted_ml = False
        ml = pump_duration_to_ml(
            duration,
            calibration["duration_"],
            calibration["bias_"],
        )

    assert isinstance(ml, (float, int))
    assert isinstance(duration, (float, int))
    assert duration >= 0, "duration should be greater than 0"

    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        dumps(
            {
                "volume_change": ml,
                "event": "add_alt_media",
                "source_of_event": source_of_event,
                "timestamp": current_utc_time(),
            }
        ),
        qos=QOS.EXACTLY_ONCE,
    )

    if user_submitted_ml:
        logger.info(f"add alt media: {round(ml,2)}mL")
    else:
        logger.info(f"add alt media: {round(duration,2)}s")

    try:
        pwm = PWM(ALT_MEDIA_PIN, calibration["hz"])
        pwm.lock()

        with catchtime() as delta_time:
            pwm.start(calibration["dc"])

        time.sleep(duration - delta_time())

    except Exception as e:
        logger.debug("Add alt media failed", exc_info=True)
        logger.error(e)
    finally:
        pwm.stop()
        pwm.cleanup()
    return ml


@click.command(name="add_alt_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_alt_media(ml, duration, source_of_event):
    """
    Add alternative media to unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return add_alt_media(ml, duration, source_of_event, unit=unit, experiment=experiment)
