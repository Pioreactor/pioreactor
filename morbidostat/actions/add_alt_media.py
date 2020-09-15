# add alt_media
import time
from json import loads
import click
import RPi.GPIO as GPIO

from morbidostat.utils import pump_ml_to_duration
from morbidostat.utils import config
from morbidostat.utils.publishing import publish


def add_alt_media(ml, unit, verbose=False):

    try:
        GPIO.setmode(GPIO.BCM)

        ALT_MEDIA_PIN = int(config["rpi_pins"][f"alt_media{unit}"])
        GPIO.setup(ALT_MEDIA_PIN, GPIO.OUT)
        GPIO.output(ALT_MEDIA_PIN, 1)  # TODO: why do I do this? Do I need this line?
        GPIO.output(ALT_MEDIA_PIN, 0)
        time.sleep(
            pump_ml_to_duration(ml, *loads(config["pump_calibration"][f"alt_media{unit}_ml_calibration"]))
        )
        GPIO.output(ALT_MEDIA_PIN, 1)

        publish(
            f"morbidostat/{unit}/io_events",
            '{"volume_change": "%s", "event": "add_alt_media"}' % ml,
            verbose=verbose,
        )
        publish(f"morbidostat/{unit}/log", f"add alt media: {ml}mL", verbose=verbose)
    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log", f"{unit} add_alt_media.py failed with {str(e)}", verbose=verbose,
        )

    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--verbose", is_flag=True, help="print to std out")
@click.argument("ml", type=float)
def click_add_alt_media(ml, unit, verbose):
    return add_alt_media(ml, unit, verbose)


if __name__ == "__main__":
    click_add_alt_media()
