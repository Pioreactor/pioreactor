# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the bioreactor algorithm.


To change the algorithm over MQTT,

topic: `morbidostat/<unit>/<experiment>/algorithm_controlling/io_algorithm/set`
message: a json object with required keyword argument. Specify the new algorithm with name `"io_algorithm"`.

To change setting over MQTT:

`morbidostat/<unit>/<experiment>/io_controlling/<setting>/set` value


"""
import time, sys, os, signal

from typing import Iterator
import json
from datetime import datetime
import time

import click
import numpy as np

from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.actions.add_alt_media import add_alt_media
from morbidostat.pubsub import publish, subscribe_and_callback, QOS

from morbidostat.utils.timing import every, RepeatedTimer
from morbidostat.utils.streaming_calculations import PID
from morbidostat.whoami import unit, experiment
from morbidostat.background_jobs.subjobs.alt_media_calculating import AltMediaCalculator
from morbidostat.background_jobs.subjobs.throughput_calculating import ThroughputCalculator
from morbidostat.background_jobs.utils import events
from morbidostat.background_jobs import BackgroundJob
from morbidostat.background_jobs.subjobs import BackgroundSubJob
from morbidostat.config import config

VIAL_VOLUME = float(config["bioreactor"]["volume_ml"])


def brief_pause():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return
    else:
        time.sleep(4)
        return


def current_time():
    return datetime.now().isoformat()


class IOAlgorithm(BackgroundSubJob):
    """
    This is the super class that algorithms inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`.


    This calls the `execute` function, which is what subclasses will define.
    TODO: change the job name?
    """

    latest_growth_rate = None
    latest_od = None
    latest_od_timestamp = None
    latest_growth_rate_timestamp = None
    latest_settings_started_at = current_time()
    latest_settings_ended_at = None
    editable_settings = ["volume", "target_od", "target_growth_rate", "duration"]

    def __init__(self, unit=None, experiment=None, verbose=0, duration=60, sensor="135/A", skip_first_run=False, **kwargs):
        super(IOAlgorithm, self).__init__(job_name="io_controlling", verbose=verbose, unit=unit, experiment=experiment)

        self.latest_event = None

        self.sensor = sensor
        self.skip_first_run = skip_first_run
        self.alt_media_calculator = AltMediaCalculator(unit=self.unit, experiment=self.experiment, verbose=self.verbose)
        self.throughput_calculator = ThroughputCalculator(unit=self.unit, experiment=self.experiment, verbose=self.verbose)
        self.sub_jobs = [self.alt_media_calculator, self.throughput_calculator]
        self.set_duration(duration)
        self.start_passive_listeners()

        publish(
            f"morbidostat/{unit}/{experiment}/log",
            f"[{self.job_name}]: starting {self.__class__.__name__} with {duration}min intervals, metadata: {kwargs}",
            verbose=verbose,
        )

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        for attr in self.editable_settings:
            if attr == "state":
                continue
            publish(f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}", None, retain=True, qos=QOS.EXACTLY_ONCE)

    def set_duration(self, value):
        self.duration = value
        try:
            self.timer_thread.cancel()
        except:
            pass
        finally:
            if self.duration is not None:
                self.timer_thread = RepeatedTimer(
                    float(self.duration) * 60, self.run, run_immediately=(not self.skip_first_run)
                ).start()

    def send_details_to_mqtt(self):
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/io_details",
            json.dumps(
                {
                    "morbidostat_unit": self.unit,
                    "experiment": self.experiment,
                    "started_at": self.latest_settings_started_at,
                    "ended_at": self.latest_settings_ended_at,
                    "algorithm": self.__class__.__name__,
                    "duration": getattr(self, "duration", None),
                    "target_od": getattr(self, "target_od", None),
                    "target_growth_rate": getattr(self, "target_growth_rate", None),
                    "volume": getattr(self, "volume", None),
                }
            ),
            qos=QOS.EXACTLY_ONCE,
            retain=True,
        )

    def on_disconnect(self):
        self.ended_at = current_time()

        try:
            self.timer_thread.cancel()
        except:
            pass
        for job in self.sub_jobs:
            job.set_state("disconnected")

        self.clear_mqtt_cache()

    def __setattr__(self, name, value) -> None:
        super(IOAlgorithm, self).__setattr__(name, value)
        if name in self.editable_settings and name != "state":
            self.latest_settings_ended_at = current_time()
            self.send_details_to_mqtt()
            self.latest_settings_started_at = current_time()
            self.latest_settings_ended_at = None

    def run(self, counter=None):
        if (self.latest_growth_rate is None) or (self.latest_od is None):
            time.sleep(5)  # wait some time for data to arrive, and try again.
            return self.run(counter=counter)

        if self.state != self.READY:
            event = events.NoEvent(f"currently in state {self.state}")

        elif (time.time() - self.most_stale_time) > 5 * 60:
            event = events.NoEvent(
                "readings are too stale (over 5 minutes old) - are `Optical density job` and `Growth rate job` running?"
            )
        else:
            event = self.execute(counter)

        publish(f"morbidostat/{self.unit}/{self.experiment}/log", f"[{self.job_name}]: triggered {event}.", verbose=self.verbose)
        self.latest_event = event
        return event

    def execute(self, counter) -> events.Event:
        raise NotImplementedError

    def execute_io_action(self, alt_media_ml=0, media_ml=0, waste_ml=0, log=True):
        assert (
            abs(alt_media_ml + media_ml - waste_ml) < 1e-5
        ), f"in order to keep same volume, IO should be equal. {alt_media_ml}, {media_ml}, {waste_ml}"

        if log:
            # TODO: this is not being stored or used.
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/io_batched",
                json.dumps({"alt_media_ml": alt_media_ml, "media_ml": media_ml, "waste_ml": waste_ml}),
                verbose=self.verbose,
            )

        max_ = 0.3
        if alt_media_ml > max_:
            self.execute_io_action(
                alt_media_ml=alt_media_ml / 2, media_ml=media_ml, waste_ml=media_ml + alt_media_ml / 2, log=False
            )
            self.execute_io_action(alt_media_ml=alt_media_ml / 2, media_ml=0, waste_ml=alt_media_ml / 2, log=False)
        elif media_ml > max_:
            self.execute_io_action(alt_media_ml=0, media_ml=media_ml / 2, waste_ml=media_ml / 2, log=False)
            self.execute_io_action(
                alt_media_ml=alt_media_ml, media_ml=media_ml / 2, waste_ml=alt_media_ml + media_ml / 2, log=False
            )
        else:
            if alt_media_ml > 0:
                add_alt_media(ml=alt_media_ml, verbose=self.verbose)
                brief_pause()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.
            if media_ml > 0:
                add_media(ml=media_ml, verbose=self.verbose)
                brief_pause()
            if waste_ml > 0:
                remove_waste(ml=waste_ml, verbose=self.verbose)
                # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
                remove_waste(duration=2, verbose=self.verbose)
                brief_pause()

    def set_growth_rate(self, message):
        self.previous_growth_rate = self.latest_growth_rate
        self.latest_growth_rate = float(message.payload)
        self.latest_growth_rate_timestamp = time.time()

    def set_OD(self, message):
        self.previous_od = self.latest_od
        self.latest_od = float(message.payload)
        self.latest_od_timestamp = time.time()

    @property
    def most_stale_time(self):
        return min(self.latest_od_timestamp, self.latest_growth_rate_timestamp)

    def start_passive_listeners(self):
        self.pubsub_clients.append(
            subscribe_and_callback(self.set_OD, f"morbidostat/{self.unit}/{self.experiment}/od_filtered/{self.sensor}")
        )
        self.pubsub_clients.append(
            subscribe_and_callback(self.set_growth_rate, f"morbidostat/{self.unit}/{self.experiment}/growth_rate")
        )


######################
# modes of operation
######################


class Silent(IOAlgorithm):
    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("never execute IO events in Silent mode")


class Turbidostat(IOAlgorithm):
    """
    turbidostat mode - try to keep cell density constant. The algorithm should run at
    near every minute (limited by the OD reading rate) to react quickly to when the target OD is hit.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(Turbidostat, self).__init__(**kwargs)
        self.target_od = target_od
        self.volume = volume

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od >= self.target_od:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(f"latest OD={self.latest_od:.2f} >= target OD={self.target_od:.2f}")
        else:
            return events.NoEvent(f"latest OD={self.latest_od:.2f} < target OD={self.target_od:.2f}")


class PIDTurbidostat(IOAlgorithm):
    """
    turbidostat mode - try to keep cell density constant using a PID target at the OD.

    The PID tells use what fraction of volume we should limit. For example, of PID
    returns 0.03, then we should remove ~97% of the volume. Choose volume to be about 1.5ml - 2.0ml.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(PIDTurbidostat, self).__init__(**kwargs)
        assert target_od is not None, "`target_od` must be set"
        assert volume is not None, "`volume` must be set"
        self.set_target_od(target_od)
        self.volume = volume

        # PID%20controller%20turbidostat.ipynb
        self.pid = PID(-2.97, -0.11, -0.09, setpoint=self.target_od, output_limits=(0, 1), sample_time=None, verbose=self.verbose)

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od <= self.min_od:
            return events.NoEvent(f"current OD, {self.latest_od:.2f}, less than OD to start diluting, {self.min_od:.2f}")
        else:
            output = self.pid.update(self.latest_od, dt=self.duration)

            volume_to_cycle = output * self.volume

            if volume_to_cycle < 0.01:
                return events.NoEvent(f"PID output={output:.2f}, so practically no volume to cycle")
            else:
                self.execute_io_action(media_ml=volume_to_cycle, waste_ml=volume_to_cycle)
                e = events.DilutionEvent(f"PID output={output:.2f}, volume to cycle={volume_to_cycle:.2f}mL")
                e.volume_to_cycle = volume_to_cycle
                e.pid_output = output
                return e

    @property
    def min_od(self):
        return 0.75 * self.target_od

    def set_target_od(self, value):
        self.target_od = float(value)
        try:
            # may not be defined yet...
            self.pid.set_setpoint(self.target_od)
        except:
            pass


class PIDMorbidostat(IOAlgorithm):
    """
    As defined in Zhong 2020
    """

    def __init__(self, target_growth_rate=None, target_od=None, volume=None, verbose=0, **kwargs):
        super(PIDMorbidostat, self).__init__(verbose=verbose, **kwargs)
        assert target_od is not None, "`target_od` must be set"
        assert target_growth_rate is not None, "`target_growth_rate` must be set"

        self.set_target_growth_rate(target_growth_rate)
        self.target_od = target_od

        Kp = config["pid_morbidostat"]["Kp"]
        Ki = config["pid_morbidostat"]["Ki"]
        Kd = config["pid_morbidostat"]["Kd"]
        self.pid = PID(
            -Kp, -Ki, -Kd, setpoint=self.target_growth_rate, output_limits=(0, 1), sample_time=None, verbose=self.verbose
        )

        if volume is not None:
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/log",
                f"[{self.job_name}]: Ignoring volume parameter; volume set by target growth rate and duration.",
                verbose=self.verbose,
            )

        self.volume = np.round(self.target_growth_rate * VIAL_VOLUME * (self.duration / 60), 4)
        self.verbose = verbose

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od <= self.min_od:
            return events.NoEvent(f"latest OD less than OD to start diluting, {self.min_od:.2f}")
        else:
            fraction_of_alt_media_to_add = self.pid.update(
                self.latest_growth_rate, dt=self.duration / 60
            )  # duration is measured in hours, not seconds (as simple_pid would want)

            # dilute more if our OD keeps creeping up - we want to stay in the linear range.
            if self.latest_od > self.max_od:
                publish(
                    f"morbidostat/{self.unit}/{self.experiment}/log",
                    f"[{self.job_name}]: executing triple dilution since we are above max OD, {self.max_od:.2f}.",
                    verbose=self.verbose,
                )
                volume = 2.5 * self.volume
            else:
                volume = self.volume

            alt_media_ml = fraction_of_alt_media_to_add * volume
            media_ml = (1 - fraction_of_alt_media_to_add) * volume

            self.execute_io_action(alt_media_ml=alt_media_ml, media_ml=media_ml, waste_ml=volume)
            event = events.AltMediaEvent(
                f"PID output={fraction_of_alt_media_to_add:.2f}, alt_media_ml={alt_media_ml:.2f}mL, media_ml={media_ml:.2f}mL"
            )
            event.media_ml = media_ml  # can be used for testing later
            event.alt_media_ml = alt_media_ml
            return event

    @property
    def min_od(self):
        return 0.7 * self.target_od

    @property
    def max_od(self):
        return 1.25 * self.target_od

    def set_target_growth_rate(self, value):
        self.target_growth_rate = float(value)
        try:
            self.pid.set_setpoint(self.target_growth_rate)
        except:
            pass


class Morbidostat(IOAlgorithm):
    """
    As defined in Toprak 2013.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(Morbidostat, self).__init__(**kwargs)
        self.target_od = target_od
        self.volume = volume

    def execute(self, *args, **kwargs) -> events.Event:
        """
        morbidostat mode - keep cell density below and threshold using chemical means. The conc.
        of the chemical is diluted slowly over time, allowing the microbes to recover.
        """
        if self.previous_od is None:
            return events.NoEvent("skip first event to wait for OD readings.")
        elif self.latest_od >= self.target_od and self.latest_od >= self.previous_od:
            # if we are above the threshold, and growth rate is greater than dilution rate
            # the second condition is an approximation of this.
            self.execute_io_action(alt_media_ml=self.volume, waste_ml=self.volume)
            return events.AltMediaEvent(
                f"latest OD, {self.latest_od:.2f} >= Target OD, {self.target_od:.2f} and Latest OD, {self.latest_od:.2f} >= Previous OD, {self.previous_od:.2f}"
            )
        else:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"latest OD, {self.latest_od:.2f} < Target OD, {self.target_od:.2f} or Latest OD, {self.latest_od:.2f} < Previous OD, {self.previous_od:.2f}"
            )


class AlgoController(BackgroundJob):

    algorithms = {
        "silent": Silent,
        "morbidostat": Morbidostat,
        "turbidostat": Turbidostat,
        "pid_turbidostat": PIDTurbidostat,
        "pid_morbidostat": PIDMorbidostat,
    }

    editable_settings = ["io_algorithm"]

    def __init__(self, io_algorithm, unit=None, experiment=None, verbose=0, **kwargs):
        super(AlgoController, self).__init__(job_name="algorithm_controlling", unit=unit, experiment=experiment, verbose=verbose)
        self.io_algorithm = io_algorithm
        self.io_algorithm_job = self.algorithms[self.io_algorithm](
            unit=self.unit, experiment=self.experiment, verbose=self.verbose, **kwargs
        )

    def set_io_algorithm(self, new_io_algorithm_json):
        try:
            algo_init = json.loads(new_io_algorithm_json)
            self.io_algorithm_job.set_state("disconnected")

            self.io_algorithm_job = self.algorithms[algo_init["io_algorithm"]](
                unit=self.unit, experiment=self.experiment, verbose=self.verbose, **algo_init
            )
            self.io_algorithm = algo_init["io_algorithm"]

        except Exception as e:
            publish(f"morbidostat/{self.unit}/{self.experiment}/error_log", f"[{self.job_name}]: failed with {e}")

    def on_disconnect(self):
        self.io_algorithm_job.set_state("disconnected")
        self.clear_mqtt_cache()

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        for attr in self.editable_settings:
            if attr == "state":
                continue
            publish(f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}", None, retain=True, qos=QOS.EXACTLY_ONCE)


def run(mode=None, duration=None, verbose=0, sensor="135/A", skip_first_run=False, **kwargs) -> Iterator[events.Event]:
    try:

        kwargs["verbose"] = verbose
        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["sensor"] = sensor
        kwargs["skip_first_run"] = skip_first_run

        controller = AlgoController(mode, **kwargs)

        while True:
            signal.pause()

    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[io_controlling]: failed {str(e)}", verbose=verbose)
        raise e


@click.command()
@click.option("--mode", default="silent", help="set the mode of the system: turbidostat, morbidostat, silent, etc.")
@click.option("--target-od", default=None, type=float)
@click.option("--target-growth-rate", default=None, type=float, help="used in PIDMorbidostat only")
@click.option("--duration", default=60, help="Time, in minutes, between every monitor check")
@click.option("--volume", default=None, help="the volume to exchange, mL", type=float)
@click.option("--sensor", default="135/A")
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally IO will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.option("--verbose", "-v", count=True, help="print to std.out")
def click_io_controlling(mode, target_od, target_growth_rate, duration, volume, sensor, skip_first_run, verbose):
    controller = run(
        mode=mode,
        target_od=target_od,
        target_growth_rate=target_growth_rate,
        duration=duration,
        volume=volume,
        skip_first_run=skip_first_run,
        sensor=sensor,
        verbose=verbose,
    )


if __name__ == "__main__":
    click_io_controlling()
