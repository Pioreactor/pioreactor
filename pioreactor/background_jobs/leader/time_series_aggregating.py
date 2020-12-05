# -*- coding: utf-8 -*-
"""
This file contains N jobs that run on the leader, and is a replacement for the NodeRed aggregation job.
"""
import signal
import time
import os
import json

import click


from pioreactor.pubsub import subscribe_and_callback, publish
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.whoami import get_unit_from_hostname, UNIVERSAL_EXPERIMENT
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
        skip_cache=False,
        job_name=DEFAULT_JOB_NAME,  # this is overwritten importantly
        record_every_n_seconds=None,  # controls how often we should sample data. Ex: growth_rate is ~5min
        write_every_n_seconds=None,  # controls how often we write to disk. Ex: about 30seconds
        time_window_seconds=None,
        **kwargs,
    ):

        super(TimeSeriesAggregation, self).__init__(job_name=job_name, **kwargs)
        self.topic = topic
        self.output_dir = output_dir
        self.aggregated_time_series = self.read(skip_cache)
        self.extract_label = extract_label
        self.time_window_seconds = time_window_seconds
        self.cache = {}

        self.write_thread = RepeatedTimer(write_every_n_seconds, self.write).start()
        self.append_cache_thread = RepeatedTimer(
            record_every_n_seconds, self.append_cache_and_clear
        ).start()

        self.start_passive_listeners()

    def on_disconnect(self):
        self.write_thread.cancel()
        self.append_cache_thread.cancel()

    @property
    def output(self):
        return self.output_dir + self.job_name + ".json"

    def read(self, skip_cache):
        if skip_cache:
            return {"series": [], "data": []}
        try:
            with open(self.output, "r") as f:
                return json.load(f)
        except Exception:
            return {"series": [], "data": []}

    def write(self):
        self.latest_write = current_time()
        with open(self.output, "w") as f:
            json.dump(self.aggregated_time_series, f)

    def append_cache_and_clear(self):
        self.update_data_series()
        self.cache = {}

    def update_data_series(self):
        time = current_time()

        for (
            label,
            latest_value,
        ) in (
            self.cache.copy().items()
        ):  # copy because a thread may try to update this while iterating.

            if label not in self.aggregated_time_series["series"]:
                self.aggregated_time_series["series"].append(label)
                self.aggregated_time_series["data"].append([])

            ix = self.aggregated_time_series["series"].index(label)
            self.aggregated_time_series["data"][ix].append({"x": time, "y": latest_value})

            if self.time_window_seconds:
                self.aggregated_time_series["data"][ix] = [
                    data
                    for data in self.aggregated_time_series["data"][ix]
                    if data["x"] > (current_time() - self.time_window_seconds * 1000)
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
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/log",
                "Only empty messages allowed to empty the cache.",
            )

    def start_passive_listeners(self):
        self.pubsub_clients.append(subscribe_and_callback(self.on_message, self.topic))
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.on_clear,  # TODO: update client
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/aggregated_time_series/set",
            )
        )


@click.command()
@click.option(
    "--output-dir",
    "-o",
    default="/home/pi/pioreactorui/backend/build/data/",
    help="the output directory",
)
@click.option("--skip-cache", is_flag=True, help="skip using the saved data on disk")
@click.option("--verbose", "-v", count=True, help="print to std.out")
def click_time_series_aggregating(output_dir, skip_cache, verbose):

    unit = get_unit_from_hostname()

    def single_sensor_label_from_topic(topic):
        split_topic = topic.split("/")
        return f"{split_topic[1]}-{split_topic[-1]}"

    def unit_from_topic(topic):
        split_topic = topic.split("/")
        return split_topic[1]

    raw135 = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/od_raw/135/+",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="od_raw_time_series_aggregating",
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=single_sensor_label_from_topic,
        write_every_n_seconds=15,
        time_window_seconds=60 * int(config["dashboard"]["raw_lookback_minutes"]),
        record_every_n_seconds=5,
    )

    filtered135 = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/od_filtered/135/+",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="od_filtered_time_series_aggregating",
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=single_sensor_label_from_topic,
        write_every_n_seconds=15,
        time_window_seconds=60 * int(config["dashboard"]["filtered_lookback_minutes"]),
        record_every_n_seconds=5,
    )

    growth_rate = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/growth_rate",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="growth_rate_time_series_aggregating",
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=unit_from_topic,
        write_every_n_seconds=15,
        record_every_n_seconds=5 * 60,  # TODO: move this to a config param
    )

    alt_media_fraction = TimeSeriesAggregation(  # noqa: F841
        "pioreactor/+/+/alt_media_calculating/alt_media_fraction",
        output_dir,
        experiment=UNIVERSAL_EXPERIMENT,
        job_name="alt_media_fraction_time_series_aggregating",
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=unit_from_topic,
        write_every_n_seconds=15,
        record_every_n_seconds=1,
    )

    while True:
        signal.pause()
