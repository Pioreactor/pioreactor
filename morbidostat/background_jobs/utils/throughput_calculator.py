# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""
import json
import time
import subprocess
import signal
import threading


from morbidostat.pubsub import publish, subscribe_and_callback, QOS
from morbidostat.whoami import unit, experiment
from morbidostat.config import leader_hostname
from typing import Optional


class ThroughputCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.

    """

    def __init__(self, unit: Optional[str] = None, experiment: Optional[str] = None, verbose: int = 0, **kwargs) -> None:
        self.unit = unit
        self.experiment = experiment
        self.verbose = verbose
        self.latest_media_throughput = {"alt_media_ml": 0, "media_ml": 0}
        self.start_passive_listeners()

    def on_io_event(self, message):
        payload = json.loads(message.payload)
        volume, event = float(payload["volume_change"]), payload["event"]
        if event == "add_media":
            self.update_media_throughput(volume, 0)
        elif event == "add_alt_media":
            self.update_media_throughput(0, volume)
        elif event == "remove_waste":
            pass
        else:
            raise ValueError("Unknown event type")

    def update_media_throughput(self, media_delta, alt_media_delta):

        self.latest_media_throughput["alt_media_ml"] += alt_media_delta
        self.latest_media_throughput["media_ml"] += media_delta

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/media_throughput",
            self.latest_media_throughput["media_ml"],
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/alt_media_throughput",
            self.latest_media_throughput["alt_media_ml"],
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/total_media_throughput",
            self.latest_media_throughput["alt_media_ml"] + self.latest_media_throughput["media_ml"],
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )
        return self.latest_media_throughput

    def set_media_initial_throughput(self, message):
        self.latest_media_throughput["media_ml"] = float(message.payload)

    def set_alt_media_initial_throughput(self, message):
        self.latest_media_throughput["alt_media_ml"] = float(message.payload)

    def start_passive_listeners(self) -> None:
        subscribe_and_callback(
            self.set_media_initial_throughput,
            f"morbidostat/{self.unit}/{self.experiment}/media_throughput",
            timeout=3,
            max_msgs=1,
        )
        subscribe_and_callback(
            self.set_alt_media_initial_throughput,
            f"morbidostat/{self.unit}/{self.experiment}/alt_media_throughput",
            timeout=3,
            max_msgs=1,
        )
        subscribe_and_callback(
            callback=self.on_io_event, topics=f"morbidostat/{self.unit}/{self.experiment}/io_events", qos=QOS.EXACTLY_ONCE
        )
