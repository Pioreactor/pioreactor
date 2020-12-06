# -*- coding: utf-8 -*-

import time, os, sys
from json import loads, dumps
import logging
import click

if "pytest" in sys.modules or os.environ.get("TESTING"):
    import fake_rpi

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

import RPi.GPIO as GPIO
from pioreactor.utils import pump_ml_to_duration, pump_duration_to_ml
from pioreactor.whoami import get_unit_from_hostname, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish, QOS

GPIO.setmode(GPIO.BCM)
logger = logging.getLogger("remove_waste")


def remove_waste(
    ml=None,
    duration=None,
    duty_cycle=33,
    source_of_event=None,
    unit=None,
    experiment=None,
):
    assert 0 <= duty_cycle <= 100
    assert (ml is not None) or (duration is not None), "Input either ml or duration"
    assert not ((ml is not None) and (duration is not None)), "Only input ml or duration"

    hz = 100
    if ml is not None:
        user_submitted_ml = True
        assert ml >= 0
        duration = pump_ml_to_duration(
            ml,
            duty_cycle,
            **loads(config["pump_calibration"][f"waste{unit}_ml_calibration"]),
        )
    elif duration is not None:
        user_submitted_ml = False
        assert duration >= 0
        ml = pump_duration_to_ml(
            duration,
            duty_cycle,
            **loads(config["pump_calibration"][f"waste{unit}_ml_calibration"]),
        )

    publish(
        f"pioreactor/{unit}/{experiment}/io_events",
        dumps(
            {
                "volume_change": ml,
                "event": "remove_waste",
                "source_of_event": source_of_event,
            }
        ),
        qos=QOS.EXACTLY_ONCE,
    )

    try:

        WASTE_PIN = int(config["rpi_pins"]["waste"])
        GPIO.setup(WASTE_PIN, GPIO.OUT)
        GPIO.output(WASTE_PIN, 0)
        pwm = GPIO.PWM(WASTE_PIN, hz)

        pwm.start(duty_cycle)
        time.sleep(duration)
        pwm.stop()

        GPIO.output(WASTE_PIN, 0)

        if user_submitted_ml is not None:
            logger.info(f"remove waste: {round(ml,2)}mL")
        else:
            logger.info(f"remove waste: {round(duration,2)}s")
    except Exception as e:
        logger.error(f"failed with {str(e)}")
        raise e

    finally:
        GPIO.cleanup(WASTE_PIN)
    return


@click.command(name="remove_waste")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--duty-cycle", default=33, type=int, show_default=True)
@click.option(
    "--source-of-event",
    default="app",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_remove_waste(ml, duration, duty_cycle, source_of_event):

    unit = get_unit_from_hostname()
    experiment = get_latest_experiment_name()

    return remove_waste(ml, duration, duty_cycle, source_of_event, unit, experiment)
