# clean tubes

import time

import click
import board
import busio
import RPi.GPIO as GPIO

from morbidostat.utils import config
from morbidostat.utils.publishing import publish


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
@click.option("--verbose", is_flag=True, help="print to std out")
def clean_tubes(unit, duration, verbose):

    GPIO.setmode(GPIO.BCM)

    try:

        for tube in ["media", "alt_media", "waste"]:
            pin = int(config["rpi_pins"][f"{tube}{unit}"])
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 1)

            publish(f"morbidostat/{unit}/log", f"[clean_tubes]: starting cleaning of {tube} tube.")

            GPIO.output(pin, 0)
            time.sleep(duration)
            GPIO.output(pin, 1)
            time.sleep(0.1)

        publish(
            f"morbidostat/{unit}/log", "[clean_tubes]: finished cleaning cycle.", verbose=verbose
        )
    except Exception as e:
        publish(f"morbidostat/{unit}/log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)
        publish(
            f"morbidostat/{unit}/error_log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose
        )
    finally:
        GPIO.cleanup()
    return


if __name__ == "__main__":
    clean_tubes()
