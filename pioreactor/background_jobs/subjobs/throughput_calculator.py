# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""

from json import loads

from pioreactor.pubsub import subscribe, QOS
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob


class ThroughputCalculator(BackgroundSubJob):
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media. Useful for knowing how much media
    has been spent, so that triggers can be set up to replace media stock.

    """

    published_settings = {
        "media_throughput": {"datatype": "float", "settable": True},
        "alt_media_throughput": {"datatype": "float", "settable": True},
    }

    def __init__(self, unit=None, experiment=None, **kwargs) -> None:
        super(ThroughputCalculator, self).__init__(
            job_name="throughput_calculator", unit=unit, experiment=experiment, **kwargs
        )

        self.media_throughput = self.get_initial_media_throughput()
        self.alt_media_throughput = self.get_initial_alt_media_throughput()

        self.start_passive_listeners()

    def on_dosing_event(self, message):
        payload = loads(message.payload)
        volume, event = float(payload["volume_change"]), payload["event"]
        if event == "add_media":
            self.update_media_throughput(volume, 0)
        elif event == "add_alt_media":
            self.update_media_throughput(0, volume)
        elif event == "remove_waste":
            pass
        else:
            raise ValueError("Unknown event type")

    def update_media_throughput(self, media_delta: float, alt_media_delta: float):

        self.alt_media_throughput += alt_media_delta
        self.media_throughput += media_delta

        return

    def get_initial_media_throughput(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/media_throughput",
            timeout=2,
        )
        if message:
            return float(message.payload)
        else:
            return 0

    def get_initial_alt_media_throughput(self) -> float:
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/alt_media_throughput",
            timeout=2,
        )
        if message:
            return float(message.payload)
        else:
            return 0

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.on_dosing_event,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
        )
