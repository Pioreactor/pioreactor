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


def remove_waste(
    ml=None,
    duration=None,
    duty_cycle=66,
    source_of_event=None,
    unit=None,
    experiment=None,
):
    logger = create_logger("remove_waste")

    assert 0 <= duty_cycle <= 100
    assert (ml is not None) or (duration is not None), "Input either ml or duration"
    assert not ((ml is not None) and (duration is not None)), "Only input ml or duration"

    try:
        config["pump_calibration"]["waste_ml_calibration"]
    except KeyError:
        logger.error(
            f"Calibration not defined. Add `waste_ml_calibration` to `pump_calibration` section to config_{unit}.ini."
        )

    hz = 100
    if ml is not None:
        user_submitted_ml = True
        assert ml >= 0
        duration = pump_ml_to_duration(
            ml, duty_cycle, **loads(config["pump_calibration"]["waste_ml_calibration"])
        )
    elif duration is not None:
        user_submitted_ml = False
        assert duration >= 0
        ml = pump_duration_to_ml(
            duration,
            duty_cycle,
            **loads(config["pump_calibration"]["waste_ml_calibration"]),
        )

    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        dumps(
            {
                "volume_change": ml,
                "event": "remove_waste",
                "source_of_event": source_of_event,
            }
        ),
        qos=QOS.EXACTLY_ONCE,
    )

    if user_submitted_ml:
        logger.info(f"{round(ml,2)}mL")
    else:
        logger.info(f"{round(duration,2)}s")

    try:

        WASTE_PIN = PWM_TO_PIN[config.getint("PWM_reverse", "waste")]
        pwm = PWM(WASTE_PIN, hz)
        pwm.lock()

        pwm.start(duty_cycle)
        time.sleep(duration)

    except Exception as e:
        logger.debug("Remove waste failed", exc_info=True)
        logger.error(e)
    finally:
        pwm.stop()
        pwm.cleanup()
    return


@click.command(name="remove_waste")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--duty-cycle", default=66, type=int, show_default=True)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - for logging",
)
def click_remove_waste(ml, duration, duty_cycle, source_of_event):
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return remove_waste(ml, duration, duty_cycle, source_of_event, unit, experiment)
