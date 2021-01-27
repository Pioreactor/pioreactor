# -*- coding: utf-8 -*-

import time, sys, os

import json
from datetime import datetime

from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.actions.add_alt_media import add_alt_media
from pioreactor.pubsub import subscribe_and_callback, QOS
from pioreactor.utils import pio_jobs_running
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.background_jobs.subjobs.alt_media_calculating import AltMediaCalculator
from pioreactor.background_jobs.subjobs.throughput_calculating import ThroughputCalculator
from pioreactor.dosing_algorithms import events
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob


def brief_pause():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return
    else:
        time.sleep(3)
        return


def current_time():
    return datetime.now().isoformat()


class DosingAlgorithm(BackgroundSubJob):
    """
    This is the super class that algorithms inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`. This calls the `execute` function, which is what subclasses will define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/dosing_algorithm/<setting>/set` value

    """

    latest_growth_rate = None
    latest_od = None
    latest_od_timestamp = None
    latest_growth_rate_timestamp = None
    latest_settings_started_at = current_time()
    latest_settings_ended_at = None
    editable_settings = ["volume", "target_od", "target_growth_rate", "duration"]

    def __init__(
        self,
        unit=None,
        experiment=None,
        duration=60,
        sensor="135/A",
        skip_first_run=False,
        **kwargs,
    ):
        super(DosingAlgorithm, self).__init__(
            job_name="dosing_algorithm", unit=unit, experiment=experiment
        )

        self.latest_event = None

        self.sensor = sensor
        self.skip_first_run = skip_first_run

        # the below subjobs should run in the "init()"?
        self.alt_media_calculator = AltMediaCalculator(
            unit=self.unit, experiment=self.experiment
        )
        self.throughput_calculator = ThroughputCalculator(
            unit=self.unit, experiment=self.experiment
        )
        self.sub_jobs = [self.alt_media_calculator, self.throughput_calculator]
        self.set_duration(duration)
        self.start_passive_listeners()

        self.logger.info(
            f"starting {self.__class__.__name__} with {duration}min intervals, metadata: {kwargs}"
        )

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        for attr in self.editable_settings:
            if attr == "state":
                continue
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.EXACTLY_ONCE,
            )

    def set_duration(self, value):
        self.duration = float(value)
        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass
        finally:
            if self.duration is not None:
                self.timer_thread = RepeatedTimer(
                    self.duration * 60,
                    self.run,
                    job_name=self.job_name,
                    run_immediately=(not self.skip_first_run),
                ).start()

    def send_details_to_mqtt(self):
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/dosing_algorithm_settings",
            json.dumps(
                {
                    "pioreactor_unit": self.unit,
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
        self.latest_settings_ended_at = current_time()
        self.send_details_to_mqtt()

        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass
        for job in self.sub_jobs:
            job.set_state("disconnected")

        self.clear_mqtt_cache()

    def __setattr__(self, name, value) -> None:
        super(DosingAlgorithm, self).__setattr__(name, value)
        if name in self.editable_settings and name != "state":
            self.latest_settings_ended_at = current_time()
            self.send_details_to_mqtt()
            self.latest_settings_started_at = current_time()
            self.latest_settings_ended_at = None

    def run(self, counter=None):
        time.sleep(10)  # wait some time for data to arrive, and try again.
        if (self.latest_growth_rate is None) or (self.latest_od is None):
            self.logger.debug("Waiting for OD and growth rate data to arrive.")
            if not ("od_reading" in pio_jobs_running()) and (
                "growth_rate_calculating" in pio_jobs_running()
            ):
                raise IOError(
                    "failed: `od_reading` and `growth_rate_calculating` should be running."
                )
            event = events.NoEvent("Waiting for OD and growth rate data to arrive.")

        elif self.state != self.READY:
            event = events.NoEvent(f"currently in state {self.state}")

        elif (time.time() - self.most_stale_time) > 5 * 60:
            event = events.NoEvent(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )
        else:
            try:
                event = self.execute(counter)
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                event = events.NoEvent("")

        self.logger.info(f"triggered {event}.")
        self.latest_event = event
        return event

    def execute(self, counter) -> events.Event:
        raise NotImplementedError

    def execute_io_action(self, alt_media_ml=0, media_ml=0, waste_ml=0):
        assert (
            abs(alt_media_ml + media_ml - waste_ml) < 1e-5
        ), f"in order to keep same volume, IO should be equal. {alt_media_ml}, {media_ml}, {waste_ml}"

        max_ = 0.3
        if alt_media_ml > max_:
            self.execute_io_action(
                alt_media_ml=alt_media_ml / 2,
                media_ml=media_ml,
                waste_ml=media_ml + alt_media_ml / 2,
            )
            self.execute_io_action(
                alt_media_ml=alt_media_ml / 2, media_ml=0, waste_ml=alt_media_ml / 2
            )
        elif media_ml > max_:
            self.execute_io_action(
                alt_media_ml=0, media_ml=media_ml / 2, waste_ml=media_ml / 2
            )
            self.execute_io_action(
                alt_media_ml=alt_media_ml,
                media_ml=media_ml / 2,
                waste_ml=alt_media_ml + media_ml / 2,
            )
        else:
            if alt_media_ml > 0:
                add_alt_media(
                    ml=alt_media_ml,
                    source_of_event="dosing_algorithm",
                    unit=self.unit,
                    experiment=self.experiment,
                )
                brief_pause()  # allow time for the addition to mix, and reduce the step response that can cause ringing in the output V.
            if media_ml > 0:
                add_media(
                    ml=media_ml,
                    source_of_event="dosing_algorithm",
                    unit=self.unit,
                    experiment=self.experiment,
                )
                brief_pause()
            if waste_ml > 0:
                remove_waste(
                    ml=waste_ml,
                    source_of_event="dosing_algorithm",
                    unit=self.unit,
                    experiment=self.experiment,
                )
                # run remove_waste for an additional few seconds to keep volume constant (determined by the length of the waste tube)
                remove_waste(
                    duration=2,
                    source_of_event="dosing_algorithm",
                    unit=self.unit,
                    experiment=self.experiment,
                )
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
            subscribe_and_callback(
                self.set_OD,
                f"pioreactor/{self.unit}/{self.experiment}/od_filtered/{self.sensor}",
                job_name=self.job_name,
            )
        )
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.set_growth_rate,
                f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
                job_name=self.job_name,
            )
        )
