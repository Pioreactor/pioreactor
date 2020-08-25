# remove waste
import time
import configparser
from json import loads
import click
import RPi.GPIO as GPIO
from paho.mqtt import publish

from morbidostat.utils import pump_ml_to_duration


config = configparser.ConfigParser()
config.read("config.ini")


def remove_waste(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        WASTE_PIN = int(config["rpi_pins"][f"waste{unit}"])
        GPIO.setup(WASTE_PIN, GPIO.OUT)
        GPIO.output(WASTE_PIN, 1)

        click.echo(click.style("starting remove_waste: %smL" % ml, fg="green"))

        GPIO.output(WASTE_PIN, 0)
        time.sleep(pump_ml_to_duration(ml, *loads(config["pump_calibration"]["waste_ml_calibration"])))
        GPIO.output(WASTE_PIN, 1)
        publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "-%s", "event": "remove_waste"}' % ml)

        publish.single(f"morbidostat/{unit}/log", "remove_waste: %smL" % ml)
        click.echo(click.style("finished remove_waste: %smL" % ml, fg="green"))
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log",)
        click.echo(click.style(f"{unit} remove_waste.py failed with {str(e)}", fg="red"))
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.argument("ml", type=float)
def click_remove_waste(ml, unit):
    return remove_waste(ml, unit)


if __name__ == "__main__":
    click_remove_waste()
