# -*- coding: utf-8 -*-
# remove waste
import time
from json import loads

import click
import RPi.GPIO as GPIO

from morbidostat.utils import pump_ml_to_duration, pump_duration_to_ml
from morbidostat.whoami import unit, experiment
from morbidostat.config import config
from morbidostat.pubsub import publish, QOS

GPIO.setmode(GPIO.BCM)


def remove_waste(ml=None, duration=None, duty_cycle=33, verbose=0):
    assert 0 <= duty_cycle <= 100
    assert (ml is not None) or (duration is not None), "Input either ml or duration"
    assert not ((ml is not None) and (duration is not None)), "Only input ml or duration"

    hz = 100
    if ml is not None:
        user_submitted_ml = True
        assert ml >= 0
        duration = pump_ml_to_duration(ml, duty_cycle, **loads(config["pump_calibration"][f"waste{unit}_ml_calibration"]))
    elif duration is not None:
        user_submitted_ml = False
        assert duration >= 0
        ml = pump_duration_to_ml(duration, duty_cycle, **loads(config["pump_calibration"][f"waste{unit}_ml_calibration"]))

    publish(
        f"morbidostat/{unit}/{experiment}/io_events",
        '{"volume_change": -%0.4f, "event": "remove_waste"}' % ml,
        verbose=verbose,
        qos=QOS.EXACTLY_ONCE,
    )

    try:
        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BCM)
        WASTE_PIN = int(config["rpi_pins"]["waste"])
        GPIO.setup(WASTE_PIN, GPIO.OUT)
        GPIO.output(WASTE_PIN, 0)
        pwm = GPIO.PWM(WASTE_PIN, hz)

        pwm.start(duty_cycle)
        time.sleep(duration)
        pwm.stop()

        GPIO.output(WASTE_PIN, 0)

        if user_submitted_ml:
            publish(f"morbidostat/{unit}/{experiment}/log", f"remove waste: {round(ml,2)}mL", verbose=verbose)
        else:
            publish(f"morbidostat/{unit}/{experiment}/log", f"remove waste: {round(duration,2)}s", verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[remove_waste]: failed with {str(e)}", verbose=verbose)
        raise e

    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--duty-cycle", default=33, type=int)
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_remove_waste(ml, duration, duty_cycle, verbose):
    return remove_waste(ml, duration, duty_cycle, verbose)


if __name__ == "__main__":
    click_remove_waste()
