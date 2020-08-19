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
@click.argument('od', type=float)
def start_monitoring(od, unit):

    verbose = True
    publish.single(f"morbidostat/{unit}/log", "starting start_monitoring.py")

    while True:
        od_ = take_od_reading(unit, verbose=0)

        if od_ > od:
            publish.single(f"morbidostat/{unit}/log", "monitor triggered IO event.")
            volume = 0.5
            remove_waste(volume, unit)
            time.sleep(2)
            add_media(volume, unit)

        time.sleep(15)


if __name__ == '__main__':
    start_monitoring()

