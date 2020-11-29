# -*- coding: utf-8 -*-
"""
This job runs on the leader, and is a replacement for the NodeRed aggregation job.
"""
import signal
import time
import os
import traceback
import click
import json


from pioreactor.pubsub import subscribe_and_callback, publish
from pioreactor.background_jobs import BackgroundJob
from pioreactor.whoami import unit, experiment, hostname
from pioreactor.config import config

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


def current_time():
    return time.time_ns() // 1_000_000


class LogAggregation(BackgroundJob):

    editable_settings = ["log_display_count"]

    def __init__(self, topics, output, log_display_count=int(config["dashboard"]["log_display_count"]), **kwargs):
        super(LogAggregation, self).__init__(job_name=JOB_NAME, **kwargs)
        self.topics = topics
        self.output = output
        self.aggregated_log_table = self.read()
        self.log_display_count = log_display_count
        self.start_passive_listeners()

    def on_message(self, message):
        try:
            unit = message.topic.split("/")[1]
            is_error = message.topic.endswith("error_log")
            self.aggregated_log_table.insert(
                0, {"timestamp": current_time(), "message": message.payload.decode(), "unit": unit, "is_error": is_error}
            )
            self.aggregated_log_table = self.aggregated_log_table[: self.log_display_count]

            self.write()
        except:
            traceback.print_exc()
        return

    def clear(self, message):
        payload = message.payload
        if not payload:
            self.aggregated_log_table = []
            self.write()
        else:
            publish(f"pioreactor/{self.unit}/{self.experiment}/log", "Only empty messages allowed to empty the log table.")

    def read(self):
        try:
            with open(self.output, "r") as f:
                return json.load(f)
        except Exception as e:
            return []

    def write(self):
        with open(self.output, "w") as f:
            json.dump(self.aggregated_log_table, f)

    def start_passive_listeners(self):
        self.pubsub_clients.append(subscribe_and_callback(self.on_message, self.topics))
        self.pubsub_clients.append(
            subscribe_and_callback(self.clear, f"pioreactor/{self.unit}/+/{self.job_name}/aggregated_log_table/set")
        )


@click.command()
@click.option(
    "--output", "-o", default="/home/pi/pioreactorui/backend/build/data/all_pioreactor.log.json", help="the output file"
)
@click.option("--verbose", "-v", count=True, help="print to std.out")
def run(output, verbose):
    logs = LogAggregation(
        [f"pioreactor/+/+/log", f"pioreactor/+/+/error_log"], output, experiment=experiment, unit=unit, verbose=verbose
    )

    while True:
        signal.pause()


if __name__ == "__main__":
    run()
