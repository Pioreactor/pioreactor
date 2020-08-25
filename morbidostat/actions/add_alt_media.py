# add alt_media
import time
import configparser
import json
import click
from paho.mqtt import publish
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read("config.ini")


def add_alt_media(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        ALT_MEDIA_PIN = int(config["rpi_pins"][f"alt_media{unit}"])
        GPIO.setup(ALT_MEDIA_PIN, GPIO.OUT)
        GPIO.output(ALT_MEDIA_PIN, 1)

        click.echo(click.style(f"starting add_alt_media: {ml}mL", fg="green"))

        ml_left = ml
        while ml_left > 1e-3:
            # hack to reduce disturbance
            ml_to_add_ = min(0.15, ml_left)
            GPIO.output(ALT_MEDIA_PIN, 0)
            time.sleep(pump_ml_to_duration(ml_to_add_, *loads(config['pump_calibration']['alt_media_ml_calibraton'])))
            GPIO.output(ALT_MEDIA_PIN, 1)
            publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "%s", "event": "add_alt_media"}' % ml_to_add_)
            time.sleep(0.1)
            ml_left -= ml_to_add_

        publish.single(f"morbidostat/{unit}/log", f"add_alt_media: {ml}mL")
        click.echo(click.style(f"finished add_alt_media: {ml}mL", fg="green"))
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
