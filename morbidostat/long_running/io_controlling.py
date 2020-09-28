# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the io algorithm
"""
import time
import signal
import sys
import threading
from enum import Enum
from typing import Iterator

import click
from simple_pid import PID

from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.actions.add_alt_media import add_alt_media
from morbidostat.utils.timing_and_threading import every
from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import get_unit_from_hostname, get_latest_experiment_name


VIAL_VOLUME = 12


class Event(Enum):
    NO_EVENT = 0
    DILUTION_EVENT = 1
    ALT_MEDIA_EVENT = 2
    FLASH_UV = 3

    def __str__(self):
        return self.name.lower().replace("_", " ")


class ControlAlgorithm:
    """
    This is the super class that algorithms inherit from. The `run` function will
    execute every N minutes (selected at the start of the program). This calls the `execute` function,
    which is what subclasses will define.
    """

    latest_rate = None
    latest_od = None

    def __init__(self, unit=None, experiment=None, verbose=False, **kwargs):
        self.unit = unit
        self.verbose = verbose
        self.experiment = experiment

    def run(self, counter=None):
        self.set_OD_measurements()
        event = self.execute(counter)
        publish(f"morbidostat/{self.unit}/{self.experiment}/log", f"[io_controlling]: triggered {event}.", verbose=self.verbose)
        return event

    def set_OD_measurements(self):
        self.previous_rate, self.previous_od = self.latest_rate, self.latest_od
        self.latest_rate = float(subscribe(f"morbidostat/{self.unit}/{self.experiment}/growth_rate").payload)
        # TODO: this below line will break when I use 135A and 135B
        self.latest_od = float(subscribe(f"morbidostat/{self.unit}/{self.experiment}/od_filtered/135").payload)
        return

    def execute(self, counter) -> Event:
        """
        Should return a member of the Event class (defined above)
        """
        raise NotImplementedError


######################
# modes of operation
######################


class Silent(ControlAlgorithm):
    def execute(self, *args, **kwargs) -> Event:
        return Event.NO_EVENT


class Turbidostat(ControlAlgorithm):
    """
    turbidostat mode - try to keep cell density constant
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        self.target_od = target_od
        self.volume = volume
        super(Turbidostat, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> Event:
        if self.latest_od >= self.target_od:
            remove_waste(ml=self.volume)
            time.sleep(0.2)
            add_media(ml=self.volume)
            return Event.DILUTION_EVENT
        else:
            return Event.NO_EVENT


class PIDTurbidostat(ControlAlgorithm):
    """
    turbidostat mode - try to keep cell density constant using a PID target at the OD.

    The PID tells use what fraction of max_volume we should limit. For example, of PID
    returns 0.03, then we should remove 97% of the max volume.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        self.target_od = target_od
        self.max_volume = volume
        self.od_to_start_diluting = 0.5
        self.pid = PID(0.07, 0.05, 0.2, setpoint=self.target_od, output_limits=(0, 1), sample_time=None)
        super(PIDTurbidostat, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> Event:
        if self.latest_od <= self.od_to_start_diluting:
            return Event.NO_EVENT
        else:
            output = self.pid(self.latest_od)
            volume_to_cycle = (1 - output) * self.max_volume
            remove_waste(ml=volume_to_cycle, verbose=self.verbose)
            time.sleep(0.2)
            add_media(ml=volume_to_cycle, verbose=self.verbose)
            return Event.DILUTION_EVENT


class Morbidostat(ControlAlgorithm):
    def __init__(self, target_od=None, volume=None, duration=None, **kwargs):
        self.target_od = target_od
        self.volume = volume
        self.duration_in_minutes = duration
        super(Morbidostat, self).__init__(**kwargs)

    @property
    def estimated_hourly_dilution_rate_(self):
        return (self.volume / VIAL_VOLUME) / (self.duration_in_minutes / 60)

    def execute(self, *args, **kwargs) -> Event:
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        if self.previous_od is None:
            return Event.NO_EVENT
        elif self.latest_od >= self.target_od and self.latest_od >= self.previous_od:
            # if we are above the threshold, and growth rate is greater than dilution rate
            # the second condition is an approximation of this.
            remove_waste(ml=self.volume, verbose=self.verbose)
            time.sleep(0.2)
            add_alt_media(ml=self.volume, verbose=self.verbose)
            return Event.ALT_MEDIA_EVENT
        else:
            remove_waste(ml=self.volume, verbose=self.verbose)
            time.sleep(0.2)
            add_media(ml=self.volume, verbose=self.verbose)
            return Event.DILUTION_EVENT


def io_controlling(mode=None, target_od=None, volume=None, duration=None, verbose=False, skip_first_run=False) -> Iterator[Event]:
    unit = get_unit_from_hostname()
    experiment = get_latest_experiment_name()

    def terminate(*args):
        publish(f"morbidostat/{unit}/{experiment}/log", f"[io_controlling]: terminated.", verbose=verbose)
        sys.exit()

    signal.signal(signal.SIGTERM, terminate)

    algorithms = {
        "silent": Silent(unit=unit, experiment=experiment, verbose=verbose),
        "morbidostat": Morbidostat(
            unit=unit, experiment=experiment, volume=volume, target_od=target_od, duration=duration, verbose=verbose
        ),
        "turbidostat": Turbidostat(unit=unit, experiment=experiment, volume=volume, target_od=target_od, verbose=verbose),
        "pid_turbidostat": PIDTurbidostat(unit=unit, experiment=experiment, volume=volume, target_od=target_od, verbose=verbose),
    }

    assert mode in algorithms.keys()

    publish(
        f"morbidostat/{unit}/{experiment}/log",
        f"[io_controlling]: starting {mode} with {duration}min intervals, target OD {target_od}V, volume {volume}mL.",
        verbose=verbose,
    )

    if skip_first_run:
        time.sleep(duration * 60)

    ##############################
    # main loop
    ##############################
    try:
        yield from every(duration * 60, algorithms[mode].run)
    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[io_controlling]: failed {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/{experiment}/log", f"[io_controlling]: failed {str(e)}", verbose=verbose)
        raise e


@click.command()
@click.option("--mode", default="silent", help="set the mode of the system: turbidostat, morbidostat, silent, etc.")
@click.option("--target_od", default=None, type=float)
@click.option("--duration", default=30, help="Time, in minutes, between every monitor check")
@click.option("--volume", default=0.25, help="the volume to exchange, mL")
@click.option(
    "--skip_first_run",
    is_flag=True,
    help="Normally IO will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.option("--verbose", is_flag=True)
def click_io_controlling(mode, target_od, duration, volume, skip_first_run, verbose):
    controller = io_controlling(
        mode=mode, target_od=target_od, duration=duration, volume=volume, skip_first_run=skip_first_run, verbose=verbose
    )
    while True:
        next(controller)


if __name__ == "__main__":
    click_io_controlling()
