"""
Continuously monitor the mordibodstat and take action. This is the core of the io algorithm
"""
import configparser
import time

import click
import board
import busio

from morbidostat.actions.take_od_reading import take_od_reading
from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from  paho.mqtt import publish



config = configparser.ConfigParser()
config.read('config.ini')


@click.command()
@click.option('--unit', default="1", help='The morbidostat unit')
def start_monitoring(unit):

    verbose = True
    publish.single(f"morbidostat/{unit}/log", "starting start_monitoring.py")

    # first, let's try keeping the culture at a constant OD
    od_constant = 1.35

    while True:
        od = take_od_reading(unit)

        if od > od_constant:
            publish.single(f"morbidostat/{unit}/log", "monitor triggered IO event.")
            volume = 0.5
            remove_waste(volume, unit)
            time.sleep(2)
            add_media(volume, unit)

        time.sleep(10)


if __name__ == '__main__':
    start_monitoring()

