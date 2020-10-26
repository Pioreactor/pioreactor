# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""
import json
import time
import subprocess
import signal
import threading

import click

from morbidostat.pubsub import publish, subscribe_and_callback, QOS
from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment
from morbidostat.config import leader_hostname
from typing import Optional

VIAL_VOLUME = 14


class AltMediaCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.

    Parameters
    -----------
    ignore_cache: ignore any retained values in the MQTT bus
    """

    def __init__(self, unit: Optional[str] = None, experiment: Optional[str] = None, verbose: int = 0, **kwargs) -> None:
        self.unit = unit
        self.experiment = experiment
        self.verbose = verbose
        self.latest_alt_media_fraction = self.get_initial_alt_media_fraction()
        self.start_passive_listeners()

    def on_io_event(self, message):
        payload = json.loads(message.payload)
        volume, event = float(payload["volume_change"]), payload["event"]
        if event == "add_media":
            self.update_alt_media_fraction(volume, 0)
        elif event == "add_alt_media":
            self.update_alt_media_fraction(0, volume)
        elif event == "remove_waste":
            pass
        else:
            raise ValueError("Unknown event type")

    def update_alt_media_fraction(self, media_delta, alt_media_delta):

        total_delta = media_delta + alt_media_delta

        # current mL
        alt_media_ml = VIAL_VOLUME * self.latest_alt_media_fraction
        media_ml = VIAL_VOLUME * (1 - self.latest_alt_media_fraction)

        # remove
        alt_media_ml = alt_media_ml * (1 - total_delta / VIAL_VOLUME)
        media_ml = media_ml * (1 - total_delta / VIAL_VOLUME)

        # add (alt) media
        alt_media_ml = alt_media_ml + alt_media_delta
        media_ml = media_ml + media_delta

        self.latest_alt_media_fraction = alt_media_ml / VIAL_VOLUME

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/alt_media_fraction",
            self.latest_alt_media_fraction,
            verbose=self.verbose,
            retain=True,
            qos=QOS.AT_LEAST_ONCE,
        )

        return self.latest_alt_media_fraction

    def get_initial_alt_media_fraction(self) -> float:
        """
        This is a hack to use a timeout (not available in paho-mqtt) to
        see if a value is present in the MQTT cache (retained message)

        Maybe I can use subscribe_and_callback and wait in the callback for a message?

        """
        test_mqtt = subprocess.run(
            [f'mosquitto_sub -t "morbidostat/{self.unit}/{self.experiment}/alt_media_fraction" -W 3 -h {leader_hostname}'],
            shell=True,
            capture_output=True,
            universal_newlines=True,
        )
        if test_mqtt.stdout == "":
            return 0.0
        else:
            return float(test_mqtt.stdout.strip())

    def start_passive_listeners(self) -> None:
        subscribe_and_callback(
            callback=self.on_io_event, topics=f"morbidostat/{self.unit}/{self.experiment}/io_events", qos=QOS.EXACTLY_ONCE
        )
