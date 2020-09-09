# clean tubes

import time
import threading
import sqlite3

import numpy as np
from scipy.optimize import curve_fit
import pandas as pd

import click
import board
import busio
import RPi.GPIO as GPIO
from paho.mqtt import publish


from morbidostat.utils import config



@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
def clean_tubes(unit, duration):

    GPIO.setmode(GPIO.BCM)

    try:

        for tube in ["media", "alt_media", "waste"]:
            pin = int(config["rpi_pins"][f"{tube}{unit}"])
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 1)

            click.echo(click.style(f"starting cleaning of {tube} tube", fg="green"))
            publish.single(f"morbidostat/{unit}/log", f"starting cleaning of {tube} tube.")

            GPIO.output(pin, 0)
            time.sleep(duration)
            GPIO.output(pin, 1)
            time.sleep(0.1)

        publish.single(f"morbidostat/{unit}/log", "finished cleaning cycle.")
    except Exception as e:
        publish.single(f"morbidostat/{unit}/log", f"clean_tubes.py failed with {str(e)}")
        publish.single(f"morbidostat/{unit}/error_log", f"clean_tubes.py failed with {str(e)}")
        click.echo(click.style(f"clean_tubes.py failed with {str(e)}", fg="red"))
    finally:
        GPIO.cleanup()
    return



if __name__ == "__main__":
    clean_tubes()
