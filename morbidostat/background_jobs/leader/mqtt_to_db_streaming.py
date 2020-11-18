# -*- coding: utf-8 -*-
"""
This job runs on the leader, and is a replacement for the NodeRed database streaming job.
"""
import signal
import time
import os
import traceback
import click
import json
from collections import namedtuple
from datetime import datetime

from sqlite3worker import Sqlite3Worker

from morbidostat.pubsub import subscribe_and_callback, publish
from morbidostat.background_jobs import BackgroundJob
from morbidostat.whoami import unit, experiment
from morbidostat.config import config

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


def current_time():
    return datetime.now().isoformat()


def produce_metadata(topic):
    SetAttrSplitTopic = namedtuple("SetAttrSplitTopic", ["morbidostat_unit", "experiment", "timestamp"])
    v = topic.split("/")
    return SetAttrSplitTopic(v[1], v[2], current_time())


class MqttToDBStreamer(BackgroundJob):
    def __init__(self, topics_and_parsers, **kwargs):
        super(MqttToDBStreamer, self).__init__(job_name=JOB_NAME, **kwargs)
        self.sqliteworker = Sqlite3Worker(config["data"]["observation_database"])
        self.topics_and_callbacks = [
            {"topic": topic_and_parser["topic"], "callback": self.create_on_message(topic_and_parser)}
            for topic_and_parser in topics_and_parsers
        ]

        self.start_passive_listeners()

    def create_on_message(self, topic_and_parser):
        def _callback(message):
            try:
                cols_to_values = topic_and_parser["parser"](message.topic, message.payload)

                cols_placeholder = ", ".join(cols_to_values.keys())
                values_placeholder = ", ".join([":" + c for c in cols_to_values.keys()])
                SQL = f"""INSERT INTO {topic_and_parser.table} ({cols_placeholder}) VALUES ({values_placeholder})"""
                print(SQL)
                self.sqliteworker.execute(SQL, cols_to_values)
            except Exception as e:
                import traceback

                traceback.print_exc()

        return _callback

    def start_passive_listeners(self):
        for topic_and_callback in self.topics_and_callbacks:
            subscribe_and_callback(topic_and_callback["callback"], topic_and_callback["topic"])


@click.command()
@click.option("--verbose", "-v", count=True, help="print to std.out")
def run(verbose):
    def parse_od(topic, payload):
        # should return a dict
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "od_reading_v": float(payload),
            "angle": "".join(topic.split("/")[-2:]),
        }

    def parse_io_events(topic, payload):
        # should return a dict
        payload = json.loads(payload)
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "volume_change": payload["volume_change"],
            "event": payload["event"],
        }

    def parse_growth_rate(topic, payload):
        # should return a dict
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "rate": float(payload),
        }

    def parse_pid_logs(topic, payload):
        metadata = produce_metadata(topic)
        payload = json.loads(payload)
        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "setpoint": payload["setpoint"],
            "output_limits_lb": payload["output_limits_lb"],
            "output_limits_ub": payload["output_limits_ub"],
            "Kd": payload["Kd"],
            "Ki": payload["Ki"],
            "Kp": payload["Kp"],
            "integral": payload["integral"],
            "proportional": payload["proportional"],
            "derivative": payload["derivative"],
            "latest_input": payload["latest_input"],
            "latest_output": payload["latest_output"],
        }

    def parse_alt_media_fraction(topic, payload):
        # should return a dict
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "alt_media_fraction": float(payload),
        }

    def parse_logs(topic, paylod):
        metadata = produce_metadata(topic)
        return {
            "experiment": metadata.experiment,
            "morbidostat_unit": metadata.morbidostat_unit,
            "timestamp": metadata.timestamp,
            "message": payload.decode(),
        }

    topics_and_parsers = [
        {"topic": "morbidostat/+/+/od_filtered/+/+", "table": "od_readings_filtered", "parser": parse_od},
        {"topic": "morbidostat/+/+/od_raw/+/+", "table": "od_readings_raw", "parser": parse_od},
        {"topic": "morbidostat/+/+/io_events", "table": "io_events", "parser": parse_io_events},
        {"topic": "morbidostat/+/+/growth_rate", "table": "io_events", "parser": parse_growth_rate},
        {"topic": "morbidostat/+/+/pid_log", "table": "pid_logs", "parser": parse_pid_logs},
        {
            "topic": "morbidostat/+/+/alt_media_calculating/alt_media_fraction",
            "table": "alt_media_fraction",
            "parser": parse_alt_media_fraction,
        },
        {"topic": "morbidostat/+/+/log", "table": "logs", "parser": parse_logs},
        {"topic": "morbidostat/+/+/error_log", "table": "logs", "parser": parse_logs},
    ]

    streamer = MqttToDBStreamer(topics_and_parsers, experiment=experiment, unit=unit, verbose=verbose)

    while True:
        signal.pause()


if __name__ == "__main__":
    run()
