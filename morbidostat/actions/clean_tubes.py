# -*- coding: utf-8 -*-
# clean tubes

import time

import click
import busio
import RPi.GPIO as GPIO

from morbidostat.config import config
from morbidostat.whoami import unit, experiment
from morbidostat.pubsub import publish


def clean_tubes(duration, verbose=0):
    GPIO.setmode(GPIO.BCM)

    try:

        for tube in ["media", "alt_media", "waste"]:
            pin = int(config["rpi_pins"][f"{tube}"])
            GPIO.setup(pin, GPIO.OUT)
            publish(f"morbidostat/{unit}/{experiment}/log", f"[clean_tubes]: starting cleaning of {tube} tube.")
            GPIO.output(pin, 1)
            time.sleep(duration)
            GPIO.output(pin, 0)
            time.sleep(0.1)

        publish(f"morbidostat/{unit}/{experiment}/log", "[clean_tubes]: finished cleaning cycle.", verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_clean_tubes(duration, verbose):
    return clean_tubes(duration, verbose)


if __name__ == "__main__":
    click_clean_tubes()
