# -*- coding: utf-8 -*-
# remove waste
import time
from json import loads

import click
import RPi.GPIO as GPIO

from morbidostat.utils import pump_ml_to_duration
from morbidostat.utils import config, get_unit_from_hostname
from morbidostat.utils.pubsub import publish


def remove_waste(ml, verbose=False):
    unit = get_unit_from_hostname()

    try:
        GPIO.setmode(GPIO.BCM)

        WASTE_PIN = int(config["rpi_pins"]["waste"])
        GPIO.setup(WASTE_PIN, GPIO.OUT)
        GPIO.output(WASTE_PIN, 1)

        GPIO.output(WASTE_PIN, 0)
        time.sleep(pump_ml_to_duration(ml, *loads(config["pump_calibration"][f"waste{unit}_ml_calibration"])))
        GPIO.output(WASTE_PIN, 1)
        publish(f"morbidostat/{unit}/io_events", '{"volume_change": "-%s", "event": "remove_waste"}' % ml, verbose=verbose)

        publish(f"morbidostat/{unit}/log", "remove waste: %smL" % ml, verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"[remove_waste]: failed with {str(e)}", verbose=verbose)
        raise e

    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--verbose", is_flag=True, help="print to std out")
@click.argument("ml", type=float)
def click_remove_waste(ml, verbose):
    return remove_waste(ml, verbose)


if __name__ == "__main__":
    click_remove_waste()
