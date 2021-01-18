# -*- coding: utf-8 -*-
import os, signal

import click
import time

import RPi.GPIO as GPIO

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT, am_I_leader
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import publish, QOS, subscribe_and_callback
from pioreactor.config import config, get_active_workers_in_inventory

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
BUTTON_PIN = config.getint("rpi_pins", "tactile_button")
LED_PIN = config.getint("rpi_pins", "led")

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LED_PIN, GPIO.OUT)


class Monitor(BackgroundJob):
    """
     - Reports metadata about the Rpi / Pioreactor back to the leader
     - controls the LED / Button interaction
     - Leader also runs this, and uses it to back up databases to other Rpis.
    """

    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)
        self.disk_usage_timer = RepeatedTimer(
            12 * 60 * 60,
            self.publish_disk_space,
            job_name=self.job_name,
            run_immediately=True,
        )

        if am_I_leader():
            self.backup_timer = RepeatedTimer(
                12 * 60 * 60,
                self.backup_db_to_other_pis,
                job_name=self.job_name,
                run_immediately=False,
            )

        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=self.button_down_and_up)

        self.start_passive_listeners()
        self.flicker_led()

    def led_on(self):
        GPIO.output(LED_PIN, GPIO.HIGH)

    def led_off(self):
        GPIO.output(LED_PIN, GPIO.LOW)

    def button_down_and_up(self, *args):
        # TODO: test
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            1,
            qos=QOS.AT_LEAST_ONCE,
        )

        self.led_on()

        publish(f"pioreactor/{self.unit}/{self.experiment}/log", "Pushed tactile button")

        while GPIO.input(BUTTON_PIN) == GPIO.HIGH:

            # we keep sending it because the user may change the webpage.
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down", 1
            )
            time.sleep(0.25)

        self.led_off()
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            0,
            qos=QOS.AT_LEAST_ONCE,
        )

    def publish_disk_space(self):
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

    def backup_db_to_other_pis(self):
        # this should only run on the leader
        assert am_I_leader(), "This should only run on the leader..."
        from sh import scp, ErrorReturnCode

        db_location = config["storage"]["observation_database"]

        n_backups = 2
        available_workers = get_active_workers_in_inventory()

        backups_complete = 0
        while (backups_complete < n_backups) and (len(available_workers) > 0):
            backup_unit = available_workers.pop()
            if backup_unit == get_unit_name():
                continue

            try:
                scp(
                    db_location,
                    f"{backup_unit}:/home/pi/.pioreactor/pioreactor.backup.sqlite",
                )
            except ErrorReturnCode:
                self.logger.error(f"Unable to backup database to {backup_unit}.")
            else:
                self.logger.debug(f"Backing up database to {backup_unit}.")
                backups_complete += 1

    def flicker_led(self, *args):
        # TODO: what happens when I hear multiple msgs in quick succession?
        self.led_on()
        time.sleep(0.2)
        self.led_off()
        time.sleep(0.2)
        self.led_on()
        time.sleep(0.2)
        self.led_off()

        time.sleep(0.5)

        self.led_on()
        time.sleep(0.2)
        self.led_off()
        time.sleep(0.2)
        self.led_on()
        time.sleep(0.2)
        self.led_off()

        time.sleep(0.5)

        self.led_on()
        time.sleep(0.2)
        self.led_off()
        time.sleep(0.2)
        self.led_on()
        time.sleep(0.2)
        self.led_off()

    def start_passive_listeners(self):

        self.pubsub_clients.append(
            subscribe_and_callback(
                self.flicker_led,
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/flicker_led",
                job_name=self.job_name,
            )
        )


@click.command(name="monitor")
def click_monitor():
    """
    Monitor and report metadata on the unit.
    """
    heidi = Monitor(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)  # noqa: F841

    signal.pause()
