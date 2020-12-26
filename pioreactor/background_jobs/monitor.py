# -*- coding: utf-8 -*-
import os, signal
import logging

import click

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import publish

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
logger = logging.getLogger(JOB_NAME)

unit = get_unit_name()


class Monitor(BackgroundJob):
    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)
        self.disk_usage_timer = RepeatedTimer(60 * 60, self.get_and_publish_disk_space)

    def get_and_publish_disk_space(self):
        import psutil

        disk_usage_percent = psutil.disk_usage("/").percent

        if disk_usage_percent <= 90:
            logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            logger.warning(f"Disk space at {disk_usage_percent}%.")
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/disk_usage_percent",
            disk_usage_percent,
        )


@click.command(name="monitor")
def click_monitor():
    """
    Start the watchdog on a unit. Reports back to the leader.
    """
    heidi = Monitor(unit=get_unit_name(), exp=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
