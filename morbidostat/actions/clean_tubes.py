# clean tubes

import configparser
import time
import threading
import sqlite3

import numpy as np
from scipy.optimize import curve_fit
import pandas as pd

import click
import GPIO
import board
import busio



from paho.mqtt import publish


config = configparser.ConfigParser()
config.read("config.ini")


@click.command()
@click.argument("target_od", type=float)
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
def clean_tubes(unit, duration):

        GPIO.setmode(GPIO.BCM)


        for tube in ['media', 'alt_media', 'waste']:
            pin = int(config["rpi_pins"][f"{tube}{unit}"])
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 1)

            click.echo(click.style(f"starting cleaning of {tube}", fg="green"))
            publish.single(f"morbidostat/{unit}/log", f"starting cleaning of {tube}.")


            GPIO.output(pin, 0)
            time.sleep(duration)
            GPIO.output(pin, 1)
            time.sleep(0.1)


        publish.single(f"morbidostat/{unit}/log", "finished cleaning cycle.")


if __name__ == "__main__":
    clean_tubes()