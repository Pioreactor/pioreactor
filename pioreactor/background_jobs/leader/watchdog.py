# -*- coding: utf-8 -*-
import os, signal
import logging

import click

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import subscribe_and_callback

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
logger = logging.getLogger(JOB_NAME)

unit = get_unit_name()


class WatchDog(BackgroundJob):
    def __init__(self, unit, experiment):
        super(WatchDog, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )

        self.start_passive_listeners()

    def watch_for_lost_state(self, msg):
        if msg.payload.decode() == self.LOST:
            # raise the alarms
            pass

    def watch_for_disk_space_percent(self, msg):
        if float(msg.payload) >= 90:
            # raise the alarms
            pass

    def start_passive_listeners(self):
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.watch_for_lost_state,
                "pioreactor/+/+/monitor/$state",
                job_name=self.job_name,
            )
        )
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.watch_for_disk_space_percent,
                "pioreactor/+/+/monitor/disk_space_percent",
                job_name=self.job_name,
            )
        )


@click.command(name="watchdog")
def click_watchdog():
    """
    Start the watchdog on the leader
    """
    heidi = WatchDog(unit=get_unit_name(), exp=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
