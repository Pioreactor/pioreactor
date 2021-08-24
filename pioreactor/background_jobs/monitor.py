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
from pioreactor.utils.gpio_helpers import GPIO_states, set_gpio_availability
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

        # set up a self check function to periodically check vitals and log them
        self.self_check_thread = RepeatedTimer(
            12 * 60 * 60, self.self_checks, job_name=self.job_name, run_immediately=True
        ).start()

        # set up GPIO for accessing the button
        self.setup_GPIO()
        self.GPIO.add_event_detect(
            BUTTON_PIN, self.GPIO.RISING, callback=self.button_down_and_up
        )

        self.start_passive_listeners()

    def setup_GPIO(self):
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
        set_gpio_availability(BUTTON_PIN, GPIO_states.GPIO_UNAVAILABLE)
        set_gpio_availability(LED_PIN, GPIO_states.GPIO_UNAVAILABLE)

    def self_checks(self):
        # watch for undervoltage problems
        self.check_for_power_problems()

        # report on CPU usage, memory, disk space
        self.publish_self_statistics()

    def check_state_of_jobs_on_machine(self):
        """
        This compares jobs that are current running on the machine, vs
        what MQTT says. In the case of a restart on leader, MQTT can get out
        of sync. We only need to run this check on startup.

        See answer here: https://iot.stackexchange.com/questions/5784/does-mosquito-broker-persist-lwt-messages-to-disk-so-they-may-be-recovered-betw
        """
        latest_exp = get_latest_experiment_name()
        whats_running = pio_jobs_running()

        def check_against_processes_running(msg):
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

        self.subscribe_and_callback(
            check_against_processes_running,
            f"pioreactor/{self.unit}/{latest_exp}/+/$state",
        )

        # let the above code run...
        sleep(2.5)

        # unsubscribe
        self.sub_client.message_callback_remove(
            f"pioreactor/{self.unit}/{latest_exp}/+/$state"
        )
        self.sub_client.unsubscribe(f"pioreactor/{self.unit}/{latest_exp}/+/$state")

        return

    def on_ready(self):
        self.flicker_led()

        # we can delay this check until ready.
        self.check_state_of_jobs_on_machine()

        self.logger.info(f"{self.unit} online and ready.")

    def on_disconnect(self):
        self.GPIO.cleanup(LED_PIN)
        self.GPIO.cleanup(BUTTON_PIN)
        set_gpio_availability(BUTTON_PIN, GPIO_states.GPIO_AVAILABLE)
        set_gpio_availability(LED_PIN, GPIO_states.GPIO_AVAILABLE)

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
            sleep(0.25)

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

        if is_testing_env():
            return

        with open("/sys/devices/platform/soc/soc:firmware/get_throttled") as file:
            status = int(file.read(), 16)

        if not currently_throttling(status):
            self.logger.debug("Power status okay.")
        else:
            self.logger.debug(f"Power status: {status_to_human_readable(status)}")

    def publish_self_statistics(self):
        import psutil

        if is_testing_env():
            return

        disk_usage_percent = round(psutil.disk_usage("/").percent)
        cpu_usage_percent = round(psutil.cpu_percent())
        available_memory_percent = round(
            100 * psutil.virtual_memory().available / psutil.virtual_memory().total
        )

        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_temperature_celcius = round(int(f.read().strip()) / 1000)

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

        if cpu_temperature_celcius <= 70:
            self.logger.debug(f"CPU temperature at {cpu_temperature_celcius} ℃.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU temperature at {cpu_temperature_celcius} ℃.")

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/computer_statistics",
            dumps(
                {
                    "disk_usage_percent": disk_usage_percent,
                    "cpu_usage_percent": cpu_usage_percent,
                    "available_memory_percent": available_memory_percent,
                    "cpu_temperature_celcius": cpu_temperature_celcius,
                }
            ),
        )

    def flicker_led(self, *args):
        # what happens when I hear multiple msgs in quick succession? Seems like calls to this function
        # are queued.

        for _ in range(4):

            self.led_on()
            sleep(0.14)
            self.led_off()
            sleep(0.14)
            self.led_on()
            sleep(0.14)
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
