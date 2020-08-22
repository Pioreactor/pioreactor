import time
import configparser
import click
from paho.mqtt import publish
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read("config.ini")


def add_alt_media(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        MEDIA_PIN = int(config["rpi_pins"][f"alt_media{unit}"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 1)

        click.echo(click.style("starting add_alt_media: %smL" % ml, fg="green"))

        GPIO.output(MEDIA_PIN, 0)
        time.sleep(ml / float(config["pump_calibration"]["media_ml_per_second"]))  # this needs to be calibrated.
        GPIO.output(MEDIA_PIN, 1)

        publish.single(f"morbidostat/{unit}/log", "add_alt_media: %smL" % ml)
        publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "%s", "event": "add_alt_media"}' % ml)
        click.echo(click.style("finished add_alt_media: %smL" % ml, fg="green"))
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"{unit} add_alt_media.py failed with {str(e)}")
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.argument("ml", type=float)
def click_add_alt_media(ml, unit):
    return add_alt_media(ml, unit)


if __name__ == "__main__":
    click_add_alt_media()
