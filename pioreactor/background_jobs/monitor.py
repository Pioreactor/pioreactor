# -*- coding: utf-8 -*-
import signal, json

import click
import time
from threading import Thread

import RPi.GPIO as GPIO

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import QOS
from pioreactor.hardware_mappings import (
    PCB_LED_PIN as LED_PIN,
    PCB_BUTTON_PIN as BUTTON_PIN,
)

GPIO.setmode(GPIO.BCM)


class Monitor(BackgroundJob):
    """
     - Reports metadata about the Rpi / Pioreactor to the leader
     - controls the LED / Button interaction
    """

    JOB_NAME = "monitor"

    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(
            job_name=self.JOB_NAME, unit=unit, experiment=experiment
        )

        # report on CPU usage, memory, disk space
        self.performance_statistics_timer = RepeatedTimer(
            12 * 60 * 60,
            self.publish_self_statistics,
            job_name=self.job_name,
            run_immediately=True,
        )
        self.performance_statistics_timer.start()

        # watch for undervoltage problems
        self.power_watchdog_thread = Thread(
            target=self.watch_for_power_problems, daemon=True
        )
        self.power_watchdog_thread.start()

        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(LED_PIN, GPIO.OUT)

        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=self.button_down_and_up)

        self.start_passive_listeners()

    def on_ready(self):
        self.flicker_led()

    def on_disconnect(self):
        self.performance_statistics_timer.cancel()
        GPIO.cleanup(LED_PIN)

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
            time.sleep(0.05)

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            0,
            qos=QOS.AT_LEAST_ONCE,
        )
        self.led_off()

    def watch_for_power_problems(self):
        # copied from https://github.com/raspberrypi/linux/pull/2397
        # and https://github.com/N2Github/Proje

        # TODO: eventually these problems should be surfaced to the user, but they
        # are too noisy atm.

        try:
            import select

            def status_to_human_readable(status):
                hr_status = []

                # if status & 0x40000:
                #     hr_status.append("Throttling has occurred.")
                # if status & 0x20000:
                #     hr_status.append("ARM frequency capping has occurred.")
                # if status & 0x10000:
                #     hr_status.append("Undervoltage has occurred.")
                if status & 0x4:
                    hr_status.append("Active throttling")
                if status & 0x2:
                    hr_status.append("Active ARM frequency capped")
                if status & 0x1:
                    hr_status.append("Active undervoltage")

                hr_status.append(
                    "Suggestion: use a larger external power supply. See docs at: https://pioreactor.com/pages/using-an-external-power-supply"
                )
                return ". ".join(hr_status)

            def currently_throttling(status):
                return (status & 0x2) or (status & 0x1) or (status & 0x4)

            def non_ignorable_status(status):
                return (status & 0x1) or (status & 0x4)

            epoll = select.epoll()
            file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
            epoll.register(file.fileno(), select.EPOLLPRI | select.EPOLLERR)
            status = int(file.read(), 16)

            if not currently_throttling(status):
                self.logger.debug("Power status okay.")
            else:
                self.logger.debug(f"Power status: {status_to_human_readable(status)}")

            while True:
                epoll.poll()
                file.seek(0)
                status = int(file.read(), 16)
                if not currently_throttling(status):
                    self.logger.debug("Power status okay.")
                else:
                    self.logger.debug(f"Power status: {status_to_human_readable(status)}")

            epoll.unregister(file.fileno())
            file.close()

        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)

    def publish_self_statistics(self):
        import psutil

        disk_usage_percent = round(psutil.disk_usage("/").percent)
        cpu_usage_percent = round(psutil.cpu_percent())
        available_memory_percent = round(
            100 * psutil.virtual_memory().available / psutil.virtual_memory().total
        )

        if disk_usage_percent <= 70:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            # TODO: add documentation  to clear disk space.
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")

        if cpu_usage_percent <= 75:
            self.logger.debug(f"CPU usage at {cpu_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU usage at {cpu_usage_percent}%.")

        if available_memory_percent <= 90:
            self.logger.debug(f"Available RAM at {available_memory_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"Available RAM at {available_memory_percent}%.")

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/computer_statistics",
            json.dumps(
                {
                    "disk_usage_percent": disk_usage_percent,
                    "cpu_usage_percent": cpu_usage_percent,
                    "available_memory_percent": available_memory_percent,
                }
            ),
        )

    def flicker_led(self, *args):
        # what happens when I hear multiple msgs in quick succession? Seems like calls to this function
        # are queued.

        for _ in range(4):

            self.led_on()
            time.sleep(0.15)
            self.led_off()
            time.sleep(0.15)
            self.led_on()
            time.sleep(0.15)
            self.led_off()
            time.sleep(0.45)

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.flicker_led,
            f"pioreactor/{self.unit}/+/{self.job_name}/flicker_led",
            qos=QOS.AT_LEAST_ONCE,
        )


@click.command(name="monitor")
def click_monitor():
    """
    Monitor and report metadata on the unit.
    """
    heidi = Monitor(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
