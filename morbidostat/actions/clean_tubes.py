# -*- coding: utf-8 -*-
# clean tubes

import time
import threading

import click
from click import echo as click_echo
import busio
import RPi.GPIO as GPIO

from morbidostat.config import config
from morbidostat.whoami import unit, experiment
from morbidostat.pubsub import publish
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.actions.add_alt_media import add_alt_media
from morbidostat.actions.add_media import add_media


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        while not self.stopped():
            self._target(*self._args, **self._kwargs)


def clean_tubes(duration, verbose=0):
    try:
        # start waste pump, poll for kill signal every N seconds
        waste_thead = StoppableThread(target=remove_waste, kwargs={"duration": 5, "duty_cycle": 100})
        waste_thead.start()
        time.sleep(3)
        add_media(duration, duty_cycle=30)
        add_alt_media(duration, duty_cycle=30)
        time.sleep(1)
        waste.stop()
        publish(f"morbidostat/{unit}/{experiment}/log", "[clean_tubes]: finished cleaning cycle.", verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[clean_tubes]: failed with {str(e)}", verbose=verbose)


@click.command()
@click.option("--duration", default=50, help="Time, in seconds, to run pumps")
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_clean_tubes(duration, verbose):
    return clean_tubes(duration, verbose)


if __name__ == "__main__":
    click_clean_tubes()
