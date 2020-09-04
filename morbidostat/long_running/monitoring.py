"""
Continuously monitor the bioreactor and take action. This is the core of the io algorithm
"""
import time
import threading

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from paho.mqtt import publish
import paho.mqtt.subscribe as subscribe

import click
import board
import busio

from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.actions.add_alt_media import add_alt_media
from morbidostat.utils.timing_and_threading import every
from morbidostat.utils import config, execute_sql_statement


@click.command()
@click.option("--mode", default="silent", help="set the mode of the system: turbidostat, mordibodstat, silent, etc.")
@click.option("--target_od", default=None, type=float)
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--duration", default=30, help="Time, in minutes, between every monitor check")
@click.option("--volume", default=0.25, help="the volume to exchange, mL")
def monitoring(mode, target_od, unit, duration, volume):

    def get_growth_rate(callback=None):
        rate = float(subscribe.simple(f"morbidostat/{unit}/growth_rate").payload)
        latest_od = float(subscribe.simple(f"morbidostat/{unit}/od_filtered").payload)

        if callback:
            callback(latest_od, rate)
        return

    ######################
    # modes of operation
    ######################
    def turbidostat(latest_od, rate, *args):
        """
        turbidostat mode - try to keep cell density constant
        """
        if latest_od > target_od and rate > 1e-10:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered dilution event.")
            time.sleep(0.2)
            remove_waste(volume, unit)
            time.sleep(0.2)
            add_media(volume, unit)
        return

    def silent(*args):
        """
        do nothing, ever
        """
        return

    def morbidostat(latest_od, rate, *args):
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        # 0.005 is basically flat.
        if latest_od > target_od and rate > 0.005:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered drug event.")
            time.sleep(0.2)
            remove_waste(volume, unit)
            time.sleep(0.2)
            add_alt_media(volume, unit)
        elif latest_od < target_od:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered dilution event.")
            time.sleep(0.2)
            remove_waste(volume, unit)
            time.sleep(0.2)
            add_media(volume, unit)
        else:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered no event.")
        return

    callbacks = {
        'silent': silent,
        'morbidostat': morbidostat,
        'turbidostat': turbidostat,
    }

    assert mode in callbacks.keys()
    assert duration > 10

    publish.single(
        f"morbidostat/{unit}/log", f"starting {mode} with {duration}min intervals, target OD {target_od}, volume {volume}"
    )

    ##############################
    # main loop
    ##############################
    try:
        every(duration * 60, get_growth_rate, callback=callbacks[mode])
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"Monitor failed: {str(e)}")
        publish.single(f"morbidostat/{unit}/log", f"Monitor failed: {str(e)}")


if __name__ == "__main__":
    monitoring()
