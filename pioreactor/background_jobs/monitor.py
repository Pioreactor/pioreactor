# -*- coding: utf-8 -*-
import os, signal

import click
import time

import RPi.GPIO as GPIO

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import publish, QOS
from pioreactor.config import config

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
BUTTON_PIN = config.getint("rpi_pins", "tactile_button")

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN)


class Monitor(BackgroundJob):
    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)
        self.disk_usage_timer = RepeatedTimer(
            6 * 60 * 60,
            self.get_and_publish_disk_space,
            job_name=self.job_name,
            run_immediately=True,
        )

        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=self.button_down_and_up)

    def button_down_and_up(self):
        # TODO: test
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            1,
            qos=QOS.AT_LEAST_ONCE,
        )
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/log",
            "Pushed tactile button",
        )
        while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            # we keep sending it because they may change the webpage.
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
                1,
                qos=QOS.AT_LEAST_ONCE,
            )
            time.sleep(0.25)

        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            0,
            qos=QOS.AT_LEAST_ONCE,
        )

    def get_and_publish_disk_space(self):
        import psutil

        disk_usage_percent = psutil.disk_usage("/").percent

        if disk_usage_percent <= 90:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/disk_usage_percent",
            disk_usage_percent,
        )


@click.command(name="monitor")
def click_monitor():
    """
    Monitor and report metadata on the unit.
    """
    heidi = Monitor(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
