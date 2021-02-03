# -*- coding: utf-8 -*-
import os, signal

import click
import time

import RPi.GPIO as GPIO

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import QOS, subscribe_and_callback
from pioreactor.hardware_mappings import (
    PCB_LED_PIN as LED_PIN,
    PCB_BUTTON_PIN as BUTTON_PIN,
)

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
GPIO.setmode(GPIO.BCM)


class Monitor(BackgroundJob):
    """
     - Reports metadata about the Rpi / Pioreactor  to the leader
     - controls the LED / Button interaction
    """

    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)
        self.disk_usage_timer = RepeatedTimer(
            12 * 60 * 60,
            self.publish_disk_space,
            job_name=self.job_name,
            run_immediately=True,
        )

        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(LED_PIN, GPIO.OUT)

        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=self.button_down_and_up)

        self.start_passive_listeners()
        self.flicker_led()

    def led_on(self):
        GPIO.output(LED_PIN, GPIO.HIGH)

    def led_off(self):
        GPIO.output(LED_PIN, GPIO.LOW)

    def button_down_and_up(self, *args):
        # Warning: this might be called twice: See "Switch debounce" in https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/
        # don't put anything that is not idempotent in here.
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            1,
            qos=QOS.AT_LEAST_ONCE,
        )

        self.led_on()

        self.logger.debug("Pushed tactile button")

        while GPIO.input(BUTTON_PIN) == GPIO.HIGH:

            # we keep sending it because the user may change the webpage.
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down", 1
            )
            time.sleep(0.25)

        self.led_off()
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            0,
            qos=QOS.AT_LEAST_ONCE,
        )

    def publish_disk_space(self):
        import psutil

        disk_usage_percent = psutil.disk_usage("/").percent

        if disk_usage_percent <= 70:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/disk_usage_percent",
            disk_usage_percent,
        )

    def flicker_led(self, *args):
        # what happens when I hear multiple msgs in quick succession? Seems like calls to this function
        # are queued.

        for _ in range(4):

            self.led_on()
            time.sleep(0.1)
            self.led_off()
            time.sleep(0.1)
            self.led_on()
            time.sleep(0.1)
            self.led_off()
            time.sleep(0.4)

    def start_passive_listeners(self):

        self.pubsub_clients.append(
            subscribe_and_callback(
                self.flicker_led,
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/flicker_led",
                job_name=self.job_name,
                qos=QOS.AT_LEAST_ONCE,
            )
        )


@click.command(name="monitor")
def click_monitor():
    """
    Monitor and report metadata on the unit.
    """
    heidi = Monitor(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
