"""
Continuously monitor the bioreactor and take action. This is the core of the io algorithm
"""
import time
import signal
import sys
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


class ControlAlgorithm:

    # init these
    latest_rate = 0
    latest_od = 0

    def run(self):
        self.set_OD_measurements()
        self.execute()
        return

    def set_OD_measurements(self):
        self.previous_rate = self.latest_rate
        self.previous_od = self.previous_od

        self.latest_rate = float(
            subscribe.simple(f"morbidostat/{unit}/growth_rate").payload
        )
        self.latest_od = float(
            subscribe.simple(f"morbidostat/{unit}/od_filtered").payload
        )
        return


######################
# modes of operation
######################


class Silent(ControlAlgorithm):
    def __init__(self, **kwargs):
        return

    def execute(self, *args, **kwargs):
        return


class Turbidostat(ControlAlgorithm):
    """
    turbidostat mode - try to keep cell density constant
    """

    def __init__(self, target_od=None, unit=None, volume=None, **kwargs):
        self.target_od = target_od
        self.unit = unit
        self.volume = volume

    def execute(self):
        if self.latest_od > self.target_od and self.latest_rate > 0:
            publish.single(
                f"morbidostat/{unit}/log", "Monitor triggered dilution event."
            )
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_media(self.volume, self.unit)
        else:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered no event.")
        return


class Morbidostat(ControlAlgorithm):
    def __init__(self, target_od=None, unit=None, volume=None, **kwargs):
        self.target_od = target_od
        self.unit = unit
        self.volume = volume

    def execute(self):
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        if self.latest_od > self.target_od and self.latest_od > self.previous_od:
            publish.single(
                f"morbidostat/{unit}/log", "Monitor triggered alt media event."
            )
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_alt_media(self.volume, self.unit)
        else:
            publish.single(
                f"morbidostat/{unit}/log", "Monitor triggered dilution event."
            )
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_media(self.volume, self.unit)
        return


@click.command()
@click.option(
    "--mode",
    default="silent",
    help="set the mode of the system: turbidostat, mordibodstat, silent, etc.",
)
@click.option("--target_od", default=None, type=float)
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option(
    "--duration", default=30, help="Time, in minutes, between every monitor check"
)
@click.option("--volume", default=0.25, help="the volume to exchange, mL")
def monitoring(mode, target_od, unit, duration, volume):

    algorithms = {
        "silent": Silent(),
        "morbidostat": Morbidostat(unit=unit, volume=volume, target_od=target_od),
        "turbidostat": Turbidostat(unit=unit, volume=volume, target_od=target_od),
    }

    assert mode in algorithms.keys()
    #assert duration > 10

    publish.single(
        f"morbidostat/{unit}/log",
        f"starting {mode} with {duration}min intervals, target OD {target_od}V, volume {volume}mL.",
    )

    ##############################
    # main loop
    ##############################
    try:
        every(duration * 60, algorithms[mode].run)
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"Monitor failed: {str(e)}")
        publish.single(f"morbidostat/{unit}/log", f"Monitor failed: {str(e)}")


def terminate(*args):
    publish.single(f"morbidostat/{unit}/log", f"Monitor terminated.")
    sys.exit()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    monitoring()
