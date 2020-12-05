# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""

from typing import Optional
import signal
import os
import click
import json


from pioreactor.pubsub import subscribe_and_callback, QOS
from pioreactor.pubsub import subscribe
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class ThroughputCalculator(BackgroundSubJob):
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media. Useful for knowing how much media
    has been spent, so that triggers can be set up to replace media stock.

    on leader:
        one source for aggregation data
        useful metric only in aggregate
    on worker
        better api (runs when io_controlling runs AND won't be dirtied with cleaning-vial events)
        used in tests (maybe an anti-pattern)
        useless metric for an individual unit, makes it hard to "reset" (i.e. if I wanted to set it back to 0 after a media exchange)
        UI has to aggregate - this is tricky: the totals are not summable.
            Sol: I need the totals, and then the deltas, or keep state of individual totals in react state, and aggregate in the render...

    """

    editable_settings = ["media_throughput", "alt_media_throughput"]

    def __init__(
        self, unit=None, experiment: Optional[str] = None, verbose: int = 0, **kwargs
    ) -> None:
        super(ThroughputCalculator, self).__init__(
            job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment
        )
        self.verbose = verbose

        self.media_throughput = self.get_initial_media_throughput()
        self.alt_media_throughput = self.get_initial_alt_media_throughput()

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

    def get_initial_alt_media_throughput(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/alt_media_throughput",
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
            )
        )


def throughput_calculating():

    calc = ThroughputCalculator()  # noqa: F841

    while True:
        signal.pause()


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
def click_throughput_calculating(verbose):
    throughput_calculating(verbose)


if __name__ == "__main__":
    click_throughput_calculating()
