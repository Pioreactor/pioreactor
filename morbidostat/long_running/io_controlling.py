"""
Continuously monitor the bioreactor and take action. This is the core of the io algorithm
"""
import time
import signal
import sys
import threading

import click
import board
import busio

from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.actions.add_alt_media import add_alt_media
from morbidostat.utils.timing_and_threading import every
from morbidostat.utils.pubsub import publish, subscribe


VIAL_VOLUME = 12


class ControlAlgorithm:

    latest_rate = None
    latest_od = None

    def run(self):
        self.set_OD_measurements()
        self.execute()
        return

    def set_OD_measurements(self):
        self.previous_rate, self.previous_od = self.latest_rate, self.latest_od

        self.latest_rate = float(subscribe(f"morbidostat/{self.unit}/growth_rate").payload)
        self.latest_od = float(subscribe(f"morbidostat/{self.unit}/od_filtered").payload)
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

    def __init__(self, target_od=None, unit=None, volume=None, duration=None, **kwargs):
        self.target_od = target_od
        self.unit = unit
        self.volume = volume
        self.duration = duration

    def execute(self):
        if self.latest_od > self.target_od and self.latest_rate > 0:
            publish(f"morbidostat/{self.unit}/log", "[io_controlling]: triggered dilution event.")
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_media(self.volume, self.unit)
        else:
            publish(f"morbidostat/{self.unit}/log", "[io_controlling]: triggered no event.")
        return


class Morbidostat(ControlAlgorithm):
    def __init__(self, target_od=None, unit=None, volume=None, duration=None, **kwargs):
        self.target_od = target_od
        self.unit = unit
        self.volume = volume
        self.duration_in_minutes = duration

    @property
    def estimated_hourly_dilution_rate_(self):
        return (self.volume / VIAL_VOLUME) / (self.duration_in_minutes / 60)

    def execute(self):
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        if self.previous_od and self.latest_od > self.target_od and self.latest_od > self.previous_od:
            # if we are above the threshold, and growth rate is greater than dilution rate
            # the second condition is an approximation of this.
            publish(f"morbidostat/{self.unit}/log", "[io_controlling]: triggered alt media event.")
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_alt_media(self.volume, self.unit)
        else:
            publish(f"morbidostat/{self.unit}/log", "[io_controlling]: triggered dilution event.")
            time.sleep(0.2)
            remove_waste(self.volume, self.unit)
            time.sleep(0.2)
            add_media(self.volume, self.unit)
        return


@click.command()
@click.argument("unit", help="The morbidostat unit")
@click.option(
    "--mode", default="silent", help="set the mode of the system: turbidostat, morbidostat, silent, etc.",
)
@click.option("--target_od", default=None, type=float)
@click.option("--duration", default=30, help="Time, in minutes, between every monitor check")
@click.option("--volume", default=0.25, help="the volume to exchange, mL")
@click.option("--verbose", is_flag=True)
def io_controlling(mode, target_od, unit, duration, volume, verbose):
    def terminate(*args):
        publish(f"morbidostat/{unit}/log", f"[io_controlling]: terminated.", verbose=verbose)
        sys.exit()

    signal.signal(signal.SIGTERM, terminate)

    algorithms = {
        "silent": Silent(),
        "morbidostat": Morbidostat(unit=unit, volume=volume, target_od=target_od, duration=duration),
        "turbidostat": Turbidostat(unit=unit, volume=volume, target_od=target_od, duration=duration),
    }

    assert mode in algorithms.keys()
    assert duration > 10

    publish(
        f"morbidostat/{unit}/log",
        f"[io_controlling]: starting {mode} with {duration}min intervals, target OD {target_od}V, volume {volume}mL.",
        verbose=verbose,
    )

    ##############################
    # main loop
    ##############################
    try:
        every(duration * 60, algorithms[mode].run)
    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"[io_controlling]: failed {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/log", f"[io_controlling]: failed {str(e)}", verbose=verbose)


if __name__ == "__main__":
    io_controlling()
