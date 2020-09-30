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


def execute_io_action(alt_media_ml=0, media_ml=0, waste_ml=0):
    assert alt_media_ml + media_ml == waste_ml, "in order to keep same volume, IO should be equal"
    pass


class ControlAlgorithm:
    """
    This is the super class that algorithms inherit from. The `run` function will
    execute every N minutes (selected at the start of the program). This calls the `execute` function,
    which is what subclasses will define.
    """

    latest_growth_rate = None
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
        self.previous_rate, self.previous_od = self.latest_growth_rate, self.latest_od
        self.latest_growth_rate = float(subscribe(f"morbidostat/{self.unit}/{self.experiment}/growth_rate").payload)
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
    turbidostat mode - try to keep cell density constant. The algorithm should run at
    near every second (limited by the OD reading rate)
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        self.target_od = target_od
        self.volume = volume
        super(Turbidostat, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> Event:
        if self.latest_od >= self.target_od:
            add_media(ml=self.volume)
            remove_waste(ml=self.volume)
            return Event.DILUTION_EVENT
        else:
            return Event.NO_EVENT


class PIDTurbidostat(ControlAlgorithm):
    """
    turbidostat mode - try to keep cell density constant using a PID target at the OD.

    The PID tells use what fraction of max_volume we should limit. For example, of PID
    returns 0.03, then we should remove 97% of the max volume. Choose max volume to be about 0.5ml.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        self.target_od = target_od
        self.max_volume = volume
        self.od_to_start_diluting = 0.75 * target_od
        self.pid = PID(0.07, 0.05, 0.2, setpoint=self.target_od, output_limits=(0, 1), sample_time=None)
        super(PIDTurbidostat, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> Event:
        if self.latest_od <= self.od_to_start_diluting:
            return Event.NO_EVENT
        else:
            output = self.pid(self.latest_od)
            volume_to_cycle = (1 - output) * self.max_volume

            if volume_to_cycle == 0:
                return Event.NO_EVENT
            else:
                add_media(ml=volume_to_cycle, verbose=self.verbose)
                remove_waste(ml=volume_to_cycle, verbose=self.verbose)
                return Event.DILUTION_EVENT


class PIDMorbidostat(ControlAlgorithm):
    """
    As defined in Zhong 2020
    """

    def __init__(self, target_growth_rate=None, target_od=None, duration=None, volume=None, **kwargs):
        super(PIDMorbidostat, self).__init__(**kwargs)
        self.target_growth_rate = target_growth_rate
        self.od_to_start_diluting = 0.75 * target_od
        self.duration = duration
        self.pid = PID(0.07, 0.05, 0.2, setpoint=self.target_growth_rate, output_limits=(0, 1), sample_time=None)

        if volume is not None:
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/log",
                f"[io_controlling]: Ignoring volume parameter; volume set by target growth rate and duration.",
                verbose=verbose,
            )

        self.volume = self.target_growth_rate * VIAL_VOLUME * (self.duration / 60)

    def execute(self, *args, **kwargs) -> Event:
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        if self.latest_od <= self.od_to_start_diluting:
            return Event.NO_EVENT
        else:
            fraction_of_media_to_add = self.pid(self.latest_growth_rate)
            add_media(ml=fraction_of_media_to_add * self.volume, verbose=self.verbose)
            add_alt_media(ml=(1 - fraction_of_media_to_add) * self.volume, verbose=self.verbose)
            remove_waste(ml=self.volume, verbose=self.verbose)
            return Event.ALT_MEDIA_EVENT


class Morbidostat(ControlAlgorithm):
    """
    As defined in Toprak 2013.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        self.target_od = target_od
        self.volume = volume
        super(Morbidostat, self).__init__(**kwargs)

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
            add_alt_media(ml=self.volume, verbose=self.verbose)
            remove_waste(ml=self.volume, verbose=self.verbose)
            return Event.ALT_MEDIA_EVENT
        else:
            add_media(ml=self.volume, verbose=self.verbose)
            remove_waste(ml=self.volume, verbose=self.verbose)
            return Event.DILUTION_EVENT


def io_controlling(
    mode=None, target_od=None, target_growth_rate=None, volume=None, duration=None, verbose=False, skip_first_run=False
) -> Iterator[Event]:
    unit = get_unit_from_hostname()
    experiment = get_latest_experiment_name()

    def terminate(*args):
        publish(f"morbidostat/{unit}/{experiment}/log", f"[io_controlling]: terminated.", verbose=verbose)
        sys.exit()

    signal.signal(signal.SIGTERM, terminate)

    algorithms = {
        "silent": Silent(unit=unit, experiment=experiment, verbose=verbose),
        "morbidostat": Morbidostat(unit=unit, experiment=experiment, volume=volume, target_od=target_od, verbose=verbose),
        "turbidostat": Turbidostat(unit=unit, experiment=experiment, volume=volume, target_od=target_od, verbose=verbose),
        "pid_turbidostat": PIDTurbidostat(unit=unit, experiment=experiment, volume=volume, target_od=target_od, verbose=verbose),
        "pid_morbidostat": PIDMorbidostat(
            unit=unit,
            experiment=experiment,
            volume=volume,
            target_od=target_od,
            duration=duration,
            target_growth_rate=target_growth_rate,
            verbose=verbose,
        ),
    }

    assert mode in algorithms.keys()

    publish(
        f"morbidostat/{unit}/{experiment}/log",
        f"[io_controlling]: starting {mode} with {duration}min intervals, target OD {target_od}V, volume {volume}mL.",
        verbose=verbose,
    )

    if skip_first_run:
        publish(f"morbidostat/{unit}/{experiment}/log", f"[io_controlling]: skipping first run", verbose=verbose)
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
@click.option("--target_growth_rate", default=None, type=float)
@click.option("--duration", default=30, help="Time, in minutes, between every monitor check")
@click.option("--volume", default=0.25, help="the volume to exchange, mL")
@click.option(
    "--skip_first_run",
    is_flag=True,
    help="Normally IO will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.option("--verbose", is_flag=True)
def click_io_controlling(mode, target_od, target_growth_rate, duration, volume, skip_first_run, verbose):
    controller = io_controlling(
        mode=mode,
        target_od=target_od,
        target_growth_rate=target_growth_rate,
        duration=duration,
        volume=volume,
        skip_first_run=skip_first_run,
        verbose=verbose,
    )
    while True:
        next(controller)


if __name__ == "__main__":
    click_io_controlling()
