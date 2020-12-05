# -*- coding: utf-8 -*-

import time, os, sys
from json import loads, dumps
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


def add_media(
    ml=None,
    duration=None,
    duty_cycle=33,
    source_of_event=None,
    verbose=0,
    unit=None,
    experiment=None,
):
    assert 0 <= duty_cycle <= 100
    assert (ml is not None) or (duration is not None)
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"

    hz = 100

    if ml is not None:
        assert ml >= 0
        duration = pump_ml_to_duration(
            ml,
            duty_cycle,
            **loads(config["pump_calibration"][f"media{unit}_ml_calibration"]),
        )
    elif duration is not None:
        ml = pump_duration_to_ml(
            duration,
            duty_cycle,
            **loads(config["pump_calibration"][f"media{unit}_ml_calibration"]),
        )
    assert duration >= 0

    publish(
        f"pioreactor/{unit}/{experiment}/io_events",
        dumps(
            {
                "volume_change": ml,
                "event": "add_media",
                "source_of_event": source_of_event,
            }
        ),
        verbose=verbose,
        qos=QOS.EXACTLY_ONCE,
    )

    try:

        MEDIA_PIN = int(config["rpi_pins"]["media"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 0)
        pwm = GPIO.PWM(MEDIA_PIN, hz)

        pwm.start(duty_cycle)
        time.sleep(duration)
        pwm.stop()

        GPIO.output(MEDIA_PIN, 0)

        if ml is not None:
            publish(
                f"pioreactor/{unit}/{experiment}/log",
                f"add media: {round(ml,2)}mL",
                verbose=verbose,
            )
        else:
            publish(
                f"pioreactor/{unit}/{experiment}/log",
                f"add media: {round(duration,2)}s",
                verbose=verbose,
            )

    except Exception as e:
        publish(
            f"pioreactor/{unit}/{experiment}/error_log",
            f"[add_media]: failed with {str(e)}",
            verbose=verbose,
        )
        raise e
    finally:
        GPIO.cleanup(MEDIA_PIN)
    return


@click.command(name="add_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--duty-cycle", default=33, type=int)
@click.option(
    "--source-of-event",
    default="app",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="print to std. out (may be redirected to pioreactor.log). Increasing values log more.",
)
def click_add_media(ml, duration, duty_cycle, source_of_event, verbose):
    unit = get_unit_from_hostname()
    experiment = get_latest_experiment_name()
    return add_media(ml, duration, duty_cycle, source_of_event, verbose, unit, experiment)
