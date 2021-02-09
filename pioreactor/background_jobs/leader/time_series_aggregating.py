# -*- coding: utf-8 -*-
"""
This file contains N jobs that run on the leader, and is a replacement for the NodeRed aggregation job.
"""
import signal
import time
import os
import json

import click


from pioreactor.pubsub import QOS
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.config import config

DEFAULT_JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


def current_time():
    return time.time_ns() // 1_000_000


class TimeSeriesAggregation(BackgroundJob):
    """
    This aggregates data _regardless_ of the experiment - users can choose to clear it (using the button), but better would
    be for the UI to clear it on new experiment creation.
    """

    def __init__(
        self,
        topic,
        output_dir,
        extract_label,
        ignore_cache=False,
        job_name=DEFAULT_JOB_NAME,  # this is overwritten importantly in instantiation
        record_every_n_seconds=None,  # controls how often we should sample data. Ex: growth_rate is ~5min
        write_every_n_seconds=None,  # controls how often we write to disk. Ex: about 30seconds
        time_window_seconds=None,
        **kwargs,
    ):

        super(TimeSeriesAggregation, self).__init__(job_name=job_name, **kwargs)
        self.topic = topic
        self.output_dir = output_dir
        self.aggregated_time_series = self.read(ignore_cache)
        self.extract_label = extract_label
        self.time_window_seconds = time_window_seconds
        self.cache = {}

        self.write_thread = RepeatedTimer(
            write_every_n_seconds, self.write, job_name=self.job_name
        ).start()
        self.append_cache_thread = RepeatedTimer(
            record_every_n_seconds, self.append_cache_and_clear, job_name=self.job_name
        ).start()

        self.start_passive_listeners()

    def on_disconnect(self):
        self.write_thread.cancel()
        self.append_cache_thread.cancel()

    @property
    def output(self):
        return self.output_dir + self.job_name + ".json"

    def read(self, ignore_cache):
        if ignore_cache:
            return {"series": [], "data": []}
        try:
            # try except hell
            with open(self.output, "r") as f:
                return json.loads(f.read())
        except (OSError, FileNotFoundError) as e:
            self.logger.debug(f"Loading failed or not found. {str(e)}")
            return {"series": [], "data": []}
        except Exception as e:
            self.logger.debug(f"Loading failed or not found. {str(e)}")
            return {"series": [], "data": []}

    def write(self):
        self.latest_write = current_time()
        with open(self.output, mode="wt") as f:
            json.dump(self.aggregated_time_series, f)

    def append_cache_and_clear(self):
        self.update_data_series()
        self.cache = {}

    def update_data_series(self):
        time = current_time()

        # .copy because a thread may try to update this while iterating.
        for (label, latest_value) in self.cache.copy().items():

            if label not in self.aggregated_time_series["series"]:
                self.aggregated_time_series["series"].append(label)
                self.aggregated_time_series["data"].append([])

            ix = self.aggregated_time_series["series"].index(label)
            self.aggregated_time_series["data"][ix].append({"x": time, "y": latest_value})

        if self.time_window_seconds:
            for ix, _ in enumerate(self.aggregated_time_series["data"]):
                # this is pretty inefficient, but okay for now.
                self.aggregated_time_series["data"][ix] = [
                    point
                    for point in self.aggregated_time_series["data"][ix]
                    if point["x"] > (current_time() - self.time_window_seconds * 1000)
                ]

    def on_message(self, message):
        label = self.extract_label(message.topic)
        try:
            self.cache[label] = float(message.payload)
        except ValueError:
            # sometimes a empty string is sent to clear the MQTT cache - that's okay - just pass.
            pass

    def on_clear(self, message):
        payload = message.payload
        if not payload:
            self.cache = {}
            self.aggregated_time_series = {"series": [], "data": []}
            self.write()
        else:
            self.logger.warning("Only empty messages allowed to empty the cache.")

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.on_message, self.topic, qos=QOS.EXACTLY_ONCE, allow_retained=False
        )
        self.subscribe_and_callback(
            self.on_clear,
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/aggregated_time_series/set",
            qos=QOS.AT_LEAST_ONCE,
        )


@click.command(name="time_series_aggregating")
@click.option(
    "--output-dir",
    "-o",
    default="/home/pi/pioreactorui/backend/build/data/",
    help="the output directory",
)
@click.option("--ignore-cache", is_flag=True, help="skip using the saved data on disk")
def click_time_series_aggregating(output_dir, ignore_cache):
    """
    (leader only) Aggregate time series for UI.

    Why do we not filter on the experiment? We want leader jobs to
    always be running without being tied to an experiment. This job would
    need to be restarted for it to pick up the new, latest experiment.

    However, when this job starts, we _don't_ want older experiments / pioreactors
    from showing up. So we don't allow retained messages.
    """
    unit = get_unit_name()

    def single_sensor_label_from_topic(topic):
        split_topic = topic.split("/")
        # return f"{split_topic[1]}-{split_topic[-2]}/{split_topic[-1]}"
        return f"{split_topic[1]}-{split_topic[-1]}"

    def unit_from_topic(topic):
        split_topic = topic.split("/")
        return split_topic[1]

    raw135 = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/od_raw/+/+",  # see note above about why we have no filter on experiment
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="od_raw_time_series_aggregating",
        unit=unit,
        ignore_cache=ignore_cache,
        extract_label=single_sensor_label_from_topic,
        write_every_n_seconds=10,
        time_window_seconds=60
        * int(config["ui.overview.settings"]["raw_od_lookback_minutes"]),
        record_every_n_seconds=5,
    )

    filtered135 = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/od_filtered/+/+",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="od_filtered_time_series_aggregating",
        unit=unit,
        ignore_cache=ignore_cache,
        extract_label=single_sensor_label_from_topic,
        write_every_n_seconds=10,
        time_window_seconds=60
        * int(config["ui.overview.settings"]["filtered_od_lookback_minutes"]),
        record_every_n_seconds=4,
    )

    growth_rate = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/growth_rate",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="growth_rate_time_series_aggregating",
        unit=unit,
        ignore_cache=ignore_cache,
        extract_label=unit_from_topic,
        write_every_n_seconds=10,
        record_every_n_seconds=3 * 60,  # TODO: move this to a config param
    )

    alt_media_fraction = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/alt_media_calculating/alt_media_fraction",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="alt_media_fraction_time_series_aggregating",
        unit=unit,
        ignore_cache=ignore_cache,
        extract_label=unit_from_topic,
        write_every_n_seconds=10,
        record_every_n_seconds=1,
    )

    while True:
        signal.pause()
