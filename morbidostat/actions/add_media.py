# add media
import time
import configparser
import click
from paho.mqtt import publish
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read("config.ini")


def add_media(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        MEDIA_PIN = int(config["rpi_pins"][f"media{unit}"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 1)

        click.echo(click.style("starting add_media: %smL" % ml, fg="green"))

        ml_left = ml
        while ml_left > 1e-3:
            # hack to reduce voltage jump
            ml_to_add_ = min(0.1, ml_left)
            GPIO.output(MEDIA_PIN, 0)
            time.sleep(ml_to_add_ / float(config["pump_calibration"]["media_ml_per_second"]))
            GPIO.output(MEDIA_PIN, 1)
            publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "%s", "event": "add_media"}' % ml_to_add_)
            time.sleep(0.1)
            ml_left -= ml_to_add_

        publish.single(f"morbidostat/{unit}/log", "add_media: %smL" % ml)
        click.echo(click.style("finished add_media: %smL" % ml, fg="green"))
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
