# -*- coding: utf-8 -*-

import time
from json import loads, dumps
import click


from pioreactor.utils import pump_ml_to_duration, pump_duration_to_ml
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish, QOS
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.logging import create_logger
from pioreactor.utils.pwm import PWM


def add_media(
    ml=None,
    duration=None,
    continuously=False,
    duty_cycle=66,
    source_of_event=None,
    unit=None,
    experiment=None,
):
    logger = create_logger("add_media")

    assert 0 <= duty_cycle <= 100
    assert (ml is not None) or (duration is not None) or (continuously)

    hz = 100

    try:
        config["pump_calibration"]["media_ml_calibration"]
    except KeyError:
        logger.error(
            f"Calibration not defined. Add `media_ml_calibration` to `pump_calibration` section to config_{unit}.ini."
        )

    if ml is not None:
        assert ml >= 0
        duration = pump_ml_to_duration(
            ml, duty_cycle, **loads(config["pump_calibration"]["media_ml_calibration"])
        )
        logger.info(f"{round(ml, 2)}mL")
    elif duration is not None:
        ml = pump_duration_to_ml(
            duration,
            duty_cycle,
            **loads(config["pump_calibration"]["media_ml_calibration"]),
        )
        logger.info(f"{round(duration, 2)}s")
    elif continuously:
        duration = 60
        ml = pump_duration_to_ml(
            duration,
            duty_cycle,
            **loads(config["pump_calibration"]["media_ml_calibration"]),
        )
        logger.info("Running pump continuously.")

    assert duration >= 0

    # publish this first, as downstream jobs need to know about it.
    json_output = dumps(
        {"volume_change": ml, "event": "add_media", "source_of_event": source_of_event}
    )
    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events", json_output, qos=QOS.EXACTLY_ONCE
    )

    try:
        MEDIA_PIN = PWM_TO_PIN[config.getint("PWM", "media")]

        pwm = PWM(MEDIA_PIN, hz)
        pwm.start(duty_cycle)

        time.sleep(duration)

        if continuously:
            while True:
                publish(
                    f"pioreactor/{unit}/{experiment}/dosing_events",
                    json_output,
                    qos=QOS.EXACTLY_ONCE,
                )
                time.sleep(duration)

    except Exception as e:
        logger.debug("Add media failed", exc_info=True)
        logger.error(e)
    finally:
        pwm.stop()
        pwm.cleanup()
    return


@click.command(name="add_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option("--duty-cycle", default=66, type=int, show_default=True)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_media(ml, duration, continuously, duty_cycle, source_of_event):
    """
    Add media to unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return add_media(
        ml, duration, continuously, duty_cycle, source_of_event, unit, experiment
    )
