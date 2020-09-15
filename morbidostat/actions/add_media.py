# add media
import time
from json import loads
import click
import RPi.GPIO as GPIO
from morbidostat.utils import pump_ml_to_duration
from morbidostat.utils import config
from morbidostat.utils.publishing import publish


def add_media(ml, unit, verbose=False):

    try:
        GPIO.setmode(GPIO.BCM)

        MEDIA_PIN = int(config["rpi_pins"][f"media{unit}"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 1)

        GPIO.output(MEDIA_PIN, 0)
        time.sleep(pump_ml_to_duration(ml, *loads(config["pump_calibration"][f"media{unit}_ml_calibration"])))
        GPIO.output(MEDIA_PIN, 1)

        publish(
            f"morbidostat/{unit}/io_events",
            '{"volume_change": "%s", "event": "add_media"}' % ml,
            verbose=verbose,
        )
        publish(f"morbidostat/{unit}/log", "add media: %smL" % ml, verbose=verbose)
    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log", f"{unit} add_media.py failed with {str(e)}", verbose=verbose,
        )
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.argument("unit", help="The morbidostat unit")
@click.option("--verbose", is_flag=True, help="print to std out")
@click.argument("ml", type=float)
def click_add_media(ml, unit, verbose):
    return add_media(ml, unit, verbose)


if __name__ == "__main__":
    click_add_media()
