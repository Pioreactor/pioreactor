# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""
from typing import Optional
import signal
import os
import click
import json


from morbidostat.pubsub import publish, subscribe_and_callback, QOS
from morbidostat.whoami import unit, experiment
from morbidostat.config import leader_hostname
from morbidostat import utils
from morbidostat.background_jobs import BackgroundJob

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class ThroughputCalculator(BackgroundJob):
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media. Useful for knowing how much media
    has been spent, so that triggers can be set up to replace media stock.

    TODO: this isn't used, and I'm not sure if this should run on leader (and aggregate all mb events),
    or on units (and the UI/other consumers aggregate on the fly).

    on leader:
        one source for aggregation data
        breaks the pattern of background jobs running on workers (hence why it's hard to design an api for the command line)
            are there other leader bj that I can think of?
            what other shared resources are there? None
        useful metric only in aggregate
    on worker
        better api (runs when io_controlling runs)
        useless metric for an individual unit, makes it hard to "reset" (i.e. if I wanted to set it back to 0 after a media exchange)
        UI has to aggregate - this is tricky: the totals are not summable.
            I would need the totals, and then the deltas, or keep state of individual totals in react state, and aggregate in the render...

    """

    editable_settings = ["media_throughput", "alt_media_throughput"]

    def __init__(self, unit=None, experiment: Optional[str] = None, verbose: int = 0, **kwargs) -> None:
        super(ThroughputCalculator, self).__init__(job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment)
        self.verbose = verbose

        self._media_throughput = 0
        self._alt_media_throughput = 0

        self.start_passive_listeners()

    @property
    def media_throughput(self):
        return self._media_throughput

    @media_throughput.setter
    def media_throughput(self, value):
        self._media_throughput = value

    @property
    def alt_media_throughput(self):
        return self._alt_media_throughput

    @alt_media_throughput.setter
    def alt_media_throughput(self, value):
        self._alt_media_throughput = value

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

        self._alt_media_throughput += alt_media_delta
        self._media_throughput += media_delta

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/media_throughput",
            self.media_throughput,
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/alt_media_throughput",
            self.alt_media_throughput,
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )
        return

    def set_media_initial_throughput(self, message):
        self.media_throughput = float(message.payload)

    def set_alt_media_initial_throughput(self, message):
        self.alt_media_throughput = float(message.payload)

    def start_passive_listeners(self) -> None:
        subscribe_and_callback(
            self.set_media_initial_throughput,
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/media_throughput",
            timeout=3,
            max_msgs=1,
        )
        subscribe_and_callback(
            self.set_alt_media_initial_throughput,
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/alt_media_throughput",
            timeout=3,
            max_msgs=1,
        )
        subscribe_and_callback(
            callback=self.on_io_event, topics=f"morbidostat/{self.unit}/{self.experiment}/io_events", qos=QOS.EXACTLY_ONCE
        )
        super(ThroughputCalculator, self).start_passive_listeners()


@utils.log_start(unit, experiment)
@utils.log_stop(unit, experiment)
def throughput_calculating():

    calc = ThroughputCalculator()

    while True:
        signal.pause()


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
def click_throughput_calculating():
    throughput_calculating(verbose)


if __name__ == "__main__":
    click_throughput_calculating()
