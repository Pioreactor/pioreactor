# -*- coding: utf-8 -*-
"""
This job runs on the leader, and is a replacement for the NodeRed aggregation job.
"""
import signal
import time
import os
import traceback
from threading import Timer
import json

import click

from morbidostat.utils import log_start, log_stop
from morbidostat.pubsub import subscribe_and_callback, publish
from morbidostat.background_jobs import BackgroundJob
from morbidostat.whoami import unit, experiment, hostname

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


def current_time():
    return time.time_ns() // 1_000_000


class TimeSeriesAggregation(BackgroundJob):
    def __init__(
        self, topic, output_dir, extract_label, skip_cache=False, every_n_minutes=None, time_window_minutes=None, **kwargs
    ):
        super(TimeSeriesAggregation, self).__init__(job_name=JOB_NAME, **kwargs)
        self.topic = topic
        self.skip_cache = skip_cache
        self.output_dir = output_dir
        self.aggregated_time_series = self.read()
        self.extract_label = extract_label
        self.time_window_minutes = time_window_minutes
        self.every_n_minutes = every_n_minutes
        self.start_passive_listeners()
        self.stream_metadata = {}

    @property
    def output(self):
        pieces = filter(lambda s: s != "+", self.topic.split("/")[3:])
        return self.output_dir + "_".join(pieces) + ".json"

    def on_message(self, message):
        received_at = current_time()
        try:
            label = self.extract_label(message.topic)

            if label not in self.aggregated_time_series["series"]:
                self.aggregated_time_series["series"].append(label)
                self.aggregated_time_series["data"].append([])
                self.stream_metadata[label] = {"earliest": received_at, "latest": received_at}

            if self.every_n_minutes:
                # check if the latest is beyond the current time - n_minutes
                # this skips the first data point.
                if (received_at - self.every_n_minutes * 60 * 1000) < self.stream_metadata[label]["latest"]:
                    return

            self.stream_metadata[label]["latest"] = received_at
            ix = self.aggregated_time_series["series"].index(label)
            self.aggregated_time_series["data"][ix].append({"x": received_at, "y": float(message.payload)})

            if self.time_window_minutes:
                self.aggregated_time_series["data"][ix] = [
                    data
                    for data in self.aggregated_time_series["data"][ix]
                    if data["x"] > (current_time() - self.time_window_minutes * 60 * 1000)
                ]
                self.stream_metadata[label]["earliest"] = current_time() - self.time_window_minutes * 60 * 1000

            self.write()
        except:
            traceback.print_exc()
        return

    def clear(self, message):
        payload = message.payload
        if not payload:
            self.aggregated_time_series = {"series": [], "data": []}
            self.write()
        else:
            publish(f"morbidostat/{self.unit}/{self.experiment}/log", "Only empty messages allowed to empty the cache.")

    def read(self):
        if self.skip_cache:
            return {"series": [], "data": []}
        try:
            with open(self.output, "r") as f:
                return json.load(f)
        except Exception as e:
            return {"series": [], "data": []}

    def write(self):
        with open(self.output, "w") as f:
            json.dump(self.aggregated_time_series, f)

    def start_passive_listeners(self):
        subscribe_and_callback(self.on_message, self.topic)
        subscribe_and_callback(
            self.clear, f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/aggregated_time_series/set"
        )


@click.command()
@click.option("--output-dir", "-o", default="/home/pi/morbidostatui/backend/build/data/", help="the output directory")
@click.option("--skip-cache", is_flag=True, help="skip using the saved data on disk")
@click.option("--verbose", "-v", count=True, help="print to std.out")
def run(output_dir, skip_cache, verbose):
    def single_sensor_label_from_topic(topic):
        split_topic = topic.split("/")
        return f"{split_topic[1]}-{split_topic[-1]}"

    def unit_from_topic(topic):
        split_topic = topic.split("/")
        return f"{split_topic[1]}"

    raw135 = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/od_raw/135/+",
        output_dir,
        experiment=experiment,
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=single_sensor_label_from_topic,
    )

    filtered135 = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/od_filtered/135/+",
        output_dir,
        experiment=experiment,
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=single_sensor_label_from_topic,
    )

    growth_rate = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/growth_rate",
        output_dir,
        experiment=experiment,
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=unit_from_topic,
    )

    alt_media_fraction = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/alt_media_calculating/alt_media_fraction",
        output_dir,
        experiment=experiment,
        unit=unit,
        verbose=verbose,
        skip_cache=skip_cache,
        extract_label=unit_from_topic,
    )

    while True:
        signal.pause()


if __name__ == "__main__":
    run()
