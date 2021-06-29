# -*- coding: utf-8 -*-
from time import sleep
from json import dumps
from sys import modules
from signal import pause

import click

from pioreactor.whoami import (
    get_unit_name,
    UNIVERSAL_EXPERIMENT,
    is_testing_env,
    get_latest_experiment_name,
)
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.pubsub import QOS
from pioreactor.hardware_mappings import (
    PCB_LED_PIN as LED_PIN,
    PCB_BUTTON_PIN as BUTTON_PIN,
)
from pioreactor.utils import pio_jobs_running

from pioreactor.version import __version__


class Monitor(BackgroundJob):
    """
    This job starts at Rpi startup, and isn't connected to any experiment. It has the following roles:

     1. Reports metadata (voltage, CPU usage, etc.) about the Rpi / Pioreactor to the leader
     2. Controls the LED / Button interaction
     3. Correction after a restart

    """

    JOB_NAME = "monitor"

    def __init__(self, unit, experiment):
        super(Monitor, self).__init__(
            job_name=self.JOB_NAME, unit=unit, experiment=experiment
        )

        self.logger.debug(f"PioreactorApp version: {__version__}")

        # report on CPU usage, memory, disk space
        self.performance_statistics_timer = RepeatedTimer(
            12 * 60 * 60,
            self.publish_self_statistics,
            job_name=self.job_name,
            run_immediately=True,
        )
        self.performance_statistics_timer.start()

        # watch for undervoltage problems
        self.power_watchdog_thread = RepeatedTimer(
            6 * 60 * 60,
            self.check_for_power_problems,
            job_name=self.job_name,
            run_immediately=True,
        )
        self.power_watchdog_thread.start()

        if is_testing_env():
            import fake_rpi

            modules["RPi"] = fake_rpi.RPi  # Fake RPi
            modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

        import RPi.GPIO as GPIO

        # I am hiding all the slow imports, but in this case, I need GPIO module
        # in many functions.
        self.GPIO = GPIO

        self.GPIO.setmode(GPIO.BCM)
        self.GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=self.GPIO.PUD_DOWN)
        self.GPIO.setup(LED_PIN, GPIO.OUT)

        self.GPIO.add_event_detect(
            BUTTON_PIN, self.GPIO.RISING, callback=self.button_down_and_up
        )

        self.start_passive_listeners()

    def check_state_of_jobs_on_machine(self):
        """
        This compares jobs that are current running on the machine, vs
        what MQTT says. In the case of a restart on leader, MQTT can get out
        of sync. We only need to run this check on startup.

        See answer here: https://iot.stackexchange.com/questions/5784/does-mosquito-broker-persist-lwt-messages-to-disk-so-they-may-be-recovered-betw
        """
        latest_exp = get_latest_experiment_name()
        whats_running = pio_jobs_running()
        probable_restart = False

        def check_against_processes_runnning(msg):
            job = msg.topic.split("/")[3]
            if (msg.payload.decode() in [self.READY, self.INIT, self.SLEEPING]) and (
                job not in whats_running
            ):
                self.publish(
                    f"pioreactor/{self.unit}/{latest_exp}/{job}/$state",
                    self.LOST,
                    retain=True,
                )
                self.logger.debug(f"Manually changing {job} state in MQTT.")
                probable_restart = True  # noqa: F841

        self.subscribe_and_callback(
            check_against_processes_runnning,
            f"pioreactor/{self.unit}/{latest_exp}/+/$state",
        )

        # let the above code run...
        sleep(5)

        if probable_restart:
            self.logger.log("Possible unexpected restart occurred?")

        return

    def on_ready(self):
        self.logger.info(f"{self.unit} online and ready.")
        self.flicker_led()

        # we can delay this check until ready.
        self.check_state_of_jobs_on_machine()

    def on_disconnect(self):
        self.GPIO.cleanup(LED_PIN)

    def led_on(self):
        self.GPIO.output(LED_PIN, self.GPIO.HIGH)

    def led_off(self):
        self.GPIO.output(LED_PIN, self.GPIO.LOW)

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

        while self.GPIO.input(BUTTON_PIN) == self.GPIO.HIGH:

            # we keep sending it because the user may change the webpage.
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down", 1
            )
            sleep(0.05)

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/button_down",
            0,
            qos=QOS.AT_LEAST_ONCE,
        )
        self.led_off()

    def check_for_power_problems(self):
        """
        Note: `get_throttled` feature isn't available on the Rpi Zero

        Sourced from https://github.com/raspberrypi/linux/pull/2397
         and https://github.com/N2Github/Proje
        """

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

        with open("/sys/devices/platform/soc/soc:firmware/get_throttled") as file:
            status = int(file.read(), 16)

        if not currently_throttling(status):
            self.logger.debug("Power status okay.")
        else:
            self.logger.debug(f"Power status: {status_to_human_readable(status)}")

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
            # TODO: add documentation to clear disk space.
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")

        if cpu_usage_percent <= 75:
            self.logger.debug(f"CPU usage at {cpu_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU usage at {cpu_usage_percent}%.")

        if available_memory_percent >= 20:
            self.logger.debug(f"Available memory at {available_memory_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"Available memory at {available_memory_percent}%.")

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/computer_statistics",
            dumps(
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
            sleep(0.15)
            self.led_off()
            sleep(0.15)
            self.led_on()
            sleep(0.15)
            self.led_off()
            sleep(0.45)

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
    Monitor(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

    pause()
