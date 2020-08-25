# add media
import time
import configparser
from json import loads
import click
from paho.mqtt import publish
import RPi.GPIO as GPIO
from morbidostat.utils import pump_ml_to_duration

config = configparser.ConfigParser()
config.read("config.ini")


def add_media(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        MEDIA_PIN = int(config["rpi_pins"][f"media{unit}"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 1)

        click.echo(click.style(f"starting add_media: {ml}mL", fg="green"))

        ml_left = ml
        while ml_left > 1e-3:
            # hack to reduce disturbance
            ml_to_add_ = min(0.15, ml_left)
            GPIO.output(MEDIA_PIN, 0)
            time.sleep(pump_ml_to_duration(ml_to_add_, *loads(config['pump_calibration']['media_ml_calibraton'])))
            GPIO.output(MEDIA_PIN, 1)
            publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "%s", "event": "add_media"}' % ml_to_add_)
            time.sleep(0.1)
            ml_left -= ml_to_add_

        publish.single(f"morbidostat/{unit}/log", "add_media: %smL" % ml)
        click.echo(click.style(f"finished add_media: {ml}mL", fg="green"))
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"{unit} add_media.py failed with {str(e)}")
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.argument("ml", type=float)
def click_add_media(ml, unit):
    return add_media(ml, unit)


if __name__ == "__main__":
    click_add_media()
