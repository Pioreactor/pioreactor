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
@click.argument('target_od', type=float)
def monitoring(target_od, unit):

    od_, odd__ = None, None
    publish.single(f"morbidostat/{unit}/log", "starting monitoring.py")

    while True:
        od_ = take_od_reading(unit, verbose=0)

        if od_ > target_od:
            publish.single(f"morbidostat/{unit}/log", "monitor triggered IO event.")
            volume = 0.5
            remove_waste(volume, unit)
            time.sleep(0.1)
            add_media(volume, unit)

        od__ = od_
        publish.single(f"morbidostat/{unit}/log", "OD rate of change: %.3f v/min." % (od_ - od__))
        time.sleep(60)


if __name__ == '__main__':
    monitoring()

