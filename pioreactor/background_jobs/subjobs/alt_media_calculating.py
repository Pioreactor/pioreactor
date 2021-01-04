# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""

import json
import os

from pioreactor.pubsub import publish, subscribe_and_callback, subscribe, QOS
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.config import config

VIAL_VOLUME = float(config["bioreactor"]["volume_ml"])
JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class AltMediaCalculator(BackgroundSubJob):
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.
    We periodically publish this, too, so the UI
    graph looks better.

    """

    def __init__(self, unit=None, experiment=None, **kwargs) -> None:
        super(AltMediaCalculator, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )
        self.unit = unit
        self.experiment = experiment
        self.latest_alt_media_fraction = self.get_initial_alt_media_fraction()

        # publish often to fill in gaps in UI chart.
        self.publish_periodically_thead = RepeatedTimer(
            5 * 60, self.publish_latest_alt_media_fraction, job_name=self.job_name
        )
        self.publish_periodically_thead.start()

        self.start_passive_listeners()

    def on_disconnect(self):
        self.publish_periodically_thead.cancel()

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

    def publish_latest_alt_media_fraction(self):
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{JOB_NAME}/alt_media_fraction",
            self.latest_alt_media_fraction,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

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
        self.publish()

        return self.latest_alt_media_fraction

    def get_initial_alt_media_fraction(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/alt_media_fraction",
            timeout=2,
        )

        if message:
            return float(message.payload)
        else:
            return 0

    def start_passive_listeners(self) -> None:
        self.pubsub_clients.append(
            subscribe_and_callback(
                callback=self.on_io_event,
                topics=f"pioreactor/{self.unit}/{self.experiment}/io_events",
                qos=QOS.EXACTLY_ONCE,
                job_name=self.job_name,
            )
        )
