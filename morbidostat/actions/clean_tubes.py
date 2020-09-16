# clean tubes

import time

import click
import busio
import RPi.GPIO as GPIO

from morbidostat.utils import config, get_unit_from_hostname
from morbidostat.utils.pubsub import publish

def clean_tubes(duration, verbose=False):
    unit = get_unit_from_hostname()

    GPIO.setmode(GPIO.BCM)

    try:

        for tube in ["media", "alt_media", "waste"]:
            pin = int(config["rpi_pins"][f"{tube}"])
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 1)

            publish(f"morbidostat/{unit}/log", f"[clean_tubes]: starting cleaning of {tube} tube.")

            GPIO.output(pin, 0)
            time.sleep(duration)
            GPIO.output(pin, 1)
            time.sleep(0.1)

        publish(f"morbidostat/{unit}/log", "[clean_tubes]: finished cleaning cycle.", verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/error_log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)
    finally:
        GPIO.cleanup()
    return

@click.command()
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
@click.option("--verbose", is_flag=True, help="print to std out")
def click_clean_tubes(duration, verbose):
    return clean_tubes(duration, verbose)

if __name__ == "__main__":
    click_clean_tubes()
