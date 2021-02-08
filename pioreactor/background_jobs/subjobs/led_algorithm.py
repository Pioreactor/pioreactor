# -*- coding: utf-8 -*-

import time, sys, os

import json
from datetime import datetime

from pioreactor.pubsub import QOS
from pioreactor.utils import pio_jobs_running
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.dosing_algorithms import events  # change later
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.config import config


def brief_pause():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return
    else:
        time.sleep(3)
        return


def current_time():
    return datetime.now().isoformat()


class LEDAlgorithm(BackgroundSubJob):
    """
    This is the super class that LED algorithms inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`. This calls the `execute` function, which is what subclasses will define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/led_algorithm/<setting>/set` value

    """

    latest_growth_rate = None
    latest_od = None
    latest_od_timestamp = None
    latest_growth_rate_timestamp = None
    latest_settings_started_at = current_time()
    latest_settings_ended_at = None
    editable_settings = ["duration"]
    edited_channels = []
    sub_jobs = []

    def __init__(
        self,
        unit=None,
        experiment=None,
        duration=60,
        sensor="135/0",
        skip_first_run=False,
        **kwargs,
    ):
        super(LEDAlgorithm, self).__init__(
            job_name="led_algorithm", unit=unit, experiment=experiment
        )

        self.latest_event = None

        self.sensor = sensor
        self.skip_first_run = skip_first_run

        self.set_duration(duration)
        self.start_passive_listeners()

        self.logger.info(
            f"starting {self.__class__.__name__} with {duration}min intervals, metadata: {kwargs}"
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

    def run(self, counter=None):
        time.sleep(8)  # wait some time for data to arrive
        if (self.latest_growth_rate is None) or (self.latest_od is None):
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not ("od_reading" in pio_jobs_running()) and (
                "growth_rate_calculating" in pio_jobs_running()
            ):
                raise IOError(
                    "failed: `od_reading` and `growth_rate_calculating` should be running."
                )
            event = events.NoEvent("waiting for OD and growth rate data to arrive")

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

    @property
    def most_stale_time(self):
        return min(self.latest_od_timestamp, self.latest_growth_rate_timestamp)

    def set_led_intensity(self, channel, intensity):
        self.edited_channels.append(channel)
        led_intensity(channel, intensity, unit=self.unit, experiment=self.experiment)

    ########## Private & internal methods

    def on_disconnect(self):
        self.latest_settings_ended_at = current_time()
        self._send_details_to_mqtt()

        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass
        for job in self.sub_jobs:
            job.set_state("disconnected")

        for channel in self.edited_channels:
            led_intensity(channel, 0, unit=self.unit, experiment=self.experiment)

        self._clear_mqtt_cache()

    def __setattr__(self, name, value) -> None:
        super(LEDAlgorithm, self).__setattr__(name, value)
        if name in self.editable_settings and name != "state":
            self.latest_settings_ended_at = current_time()
            self._send_details_to_mqtt()
            self.latest_settings_started_at = current_time()
            self.latest_settings_ended_at = None

    def _set_growth_rate(self, message):
        self.previous_growth_rate = self.latest_growth_rate
        self.latest_growth_rate = float(message.payload)
        self.latest_growth_rate_timestamp = time.time()

    def _set_OD(self, message):
        self.previous_od = self.latest_od
        self.latest_od = float(message.payload)
        self.latest_od_timestamp = time.time()

    def _clear_mqtt_cache(self):
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

    def _send_details_to_mqtt(self):
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/led_algorithm_settings",
            json.dumps(
                {
                    "pioreactor_unit": self.unit,
                    "experiment": self.experiment,
                    "started_at": self.latest_settings_started_at,
                    "ended_at": self.latest_settings_ended_at,
                    "algorithm": self.__class__.__name__,
                    "settings": json.dumps(
                        {
                            attr: getattr(self, attr, None)
                            for attr in self.editable_settings
                            if attr != "state"
                        }
                    ),
                }
            ),
            qos=QOS.EXACTLY_ONCE,
            retain=True,
        )

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self._set_OD,
            f"pioreactor/{self.unit}/{self.experiment}/od_filtered/{self.sensor}",
        )
        self.subscribe_and_callback(
            self._set_growth_rate, f"pioreactor/{self.unit}/{self.experiment}/growth_rate"
        )


# not tested, experimental


class Silent(LEDAlgorithm):
    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("nothing occurs in Silent.")


class TrackOD(LEDAlgorithm):
    def __init__(self, **kwargs):
        super(TrackOD, self).__init__(**kwargs)

        self.white_light = config.get("leds", "white_light")
        # set luminosity to 10% initially
        self.set_led_intensity(self.white_light, 0.1)

    def execute(self, *args, **kwargs) -> events.Event:
        self.set_led_intensity(self.white_light, 0.1 * (self.latest_od - 1) + 0.1)
        return events.IncreasedLuminosity(
            f"new output:{0.1 * (self.latest_od - 1) + 0.1}"
        )


class FlashUV(LEDAlgorithm):
    def __init__(self, **kwargs):
        super(FlashUV, self).__init__(**kwargs)
        self.uv_led = config.get("leds", "uv380")

        self.set_led_intensity(self.uv_led, 0)

    def execute(self, *args, **kwargs) -> events.Event:
        self.set_led_intensity(self.uv_led, 100)
        time.sleep(1)
        self.set_led_intensity(self.uv_led, 0)
        return events.UvFlash("Flashed UV for 1 second")
