# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from json import loads
from time import sleep
from typing import Optional

import click

from pioreactor import config
from pioreactor import error_codes
from pioreactor import utils
from pioreactor import version
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware import PCB_BUTTON_PIN as BUTTON_PIN
from pioreactor.hardware import PCB_LED_PIN as LED_PIN
from pioreactor.hardware import TEMP
from pioreactor.pubsub import QOS
from pioreactor.types import MQTTMessage
from pioreactor.utils.gpio_helpers import set_gpio_availability
from pioreactor.utils.networking import get_ip
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer


class Monitor(BackgroundJob):
    """
    This job starts at Rpi startup, and isn't connected to any experiment. It has the following roles:

     1. Reports metadata (voltage, CPU usage, etc.) about the Rpi / Pioreactor to the leader
     2. Controls the LED / Button interaction
     3. Correction after a restart
     4. Check database backup if leader
     5. Use the LED blinks to report error codes to the user, see error_codes module
        can also be invoked with the MQTT topic:
         pioreactor/{unit}/+/monitor/flicker_led_with_error_code   error_code as message
     6. Listens to MQTT for job to start, on the topic
         pioreactor/{unit}/$experiment/run/{job_name}   json-encoded args as message

    """

    published_settings = {
        "computer_statistics": {"datatype": "json", "settable": False},
        "button_down": {"datatype": "boolean", "settable": False},
    }
    computer_statistics: Optional[dict] = None
    led_in_use: bool = False

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(job_name="monitor", unit=unit, experiment=experiment)

        def pretty_version(info: tuple[int, ...]) -> str:
            return ".".join((str(x) for x in info))

        self.logger.debug(
            f"Pioreactor software version: {pretty_version(version.software_version_info)}"
        )
        self.logger.debug(
            f"Pioreactor HAT version: {pretty_version(version.hardware_version_info)}"
        )

        self.button_down = False
        # set up GPIO for accessing the button and changing the LED
        self.setup_GPIO()

        # set up a self check function to periodically check vitals and log them
        # we manually run a self_check outside of a thread first, as if there are
        # problems detected, we may want to block and not let the job continue.
        self.self_checks()
        self.self_check_thread = RepeatedTimer(
            6 * 60 * 60,
            self.self_checks,
            job_name=self.job_name,
            run_immediately=False,
        ).start()

        self.start_passive_listeners()

    def setup_GPIO(self) -> None:
        set_gpio_availability(BUTTON_PIN, False)
        set_gpio_availability(LED_PIN, False)

        import RPi.GPIO as GPIO  # type: ignore

        # I am hiding all the slow imports, but in this case, I need GPIO module
        # in many functions.
        self.GPIO = GPIO

        self.GPIO.setmode(GPIO.BCM)
        self.GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=self.GPIO.PUD_DOWN)
        self.GPIO.setup(LED_PIN, GPIO.OUT)
        try:
            self.GPIO.add_event_detect(
                BUTTON_PIN,
                self.GPIO.RISING,
                callback=self.button_down_and_up,
                bouncetime=200,
            )
        except RuntimeError:
            self.logger.debug("Failed to add button detect.", exc_info=True)
            self.logger.warning("Failed to add button detect.")

    def check_for_network(self) -> None:
        ip = get_ip()
        while (not whoami.is_testing_env()) and ((ip == "127.0.0.1") or (ip is None)):
            # no wifi connection? Sound the alarm.
            self.logger.warning("Unable to connect to network...")
            self.flicker_led_with_error_code(error_codes.NO_NETWORK_CONNECTION)
            ip = get_ip()

    def self_checks(self) -> None:
        # check active network connection
        self.check_for_network()

        # watch for undervoltage problems
        self.check_for_power_problems()

        # report on CPU usage, memory, disk space
        self.publish_self_statistics()

        if whoami.am_I_leader():
            # report on last database backup, if leader
            self.check_for_last_backup()

        if whoami.am_I_active_worker():
            # check the PCB temperature
            self.check_heater_pcb_temperature()

        if not whoami.am_I_leader():
            # check for MQTT connection to leader
            self.check_for_mqtt_connection_to_leader()

    def check_heater_pcb_temperature(self) -> None:
        """
        Originally from #220
        """
        if whoami.is_testing_env():
            from pioreactor.utils.mock import MockTMP1075 as TMP1075
        else:
            from TMP1075 import TMP1075  # type: ignore

        try:
            tmp_driver = TMP1075(address=TEMP)
        except ValueError:
            # No PCB detected using i2c - fine to exit.
            return

        observed_tmp = tmp_driver.get_temperature()

        if observed_tmp >= 64.0:
            # something is wrong - temperature_control should have detected this, but didn't, so it must have failed / incorrectly cleaned up.
            # we're going to just shutdown to be safe.
            from subprocess import call

            self.logger.error(
                f"Detected an extremely high temperature, {observed_tmp} ℃ on the heating PCB - shutting down for safety."
            )

            call("sudo shutdown now --poweroff", shell=True)
        self.logger.debug(f"Heating PCB temperature at {observed_tmp} ℃.")

    def check_for_mqtt_connection_to_leader(self) -> None:
        while (not self.pub_client.is_connected()) or (not self.sub_client.is_connected()):
            self.logger.warning(
                f"""Not able to connect MQTT clients to leader.
1. Is the leader, {config.leader_hostname} at {config.leader_address}, in config.ini correct?
2. Is the Pioreactor leader online and responsive?
"""
            )  # remember, this doesn't get published to leader...

            self.set_state(self.LOST)
            self.flicker_led_with_error_code(
                error_codes.MQTT_CLIENT_NOT_CONNECTED_TO_LEADER_ERROR_CODE
            )

    def check_for_last_backup(self) -> None:

        with utils.local_persistant_storage("database_backups") as cache:
            if cache.get("latest_backup_timestamp"):
                latest_backup_at = datetime.strptime(
                    cache["latest_backup_timestamp"].decode("utf-8"),
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                )

                if (datetime.utcnow() - latest_backup_at).days > 30:
                    self.logger.warning("Database hasn't been backed up in over 30 days.")

    def check_state_of_jobs_on_machine(self) -> None:
        """
        This compares jobs that are current running on the machine, vs
        what MQTT says. In the case of a restart on leader, MQTT can get out
        of sync. We only need to run this check on startup.

        See answer here: https://iot.stackexchange.com/questions/5784/does-mosquito-broker-persist-lwt-messages-to-disk-so-they-may-be-recovered-betw
        """
        latest_exp = whoami._get_latest_experiment_name()

        def check_against_processes_running(msg: MQTTMessage) -> None:
            job = msg.topic.split("/")[3]
            if (msg.payload.decode() in [self.READY, self.INIT, self.SLEEPING]) and (
                not utils.is_pio_job_running(job)
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
        self.sub_client.message_callback_remove(f"pioreactor/{self.unit}/{latest_exp}/+/$state")
        self.sub_client.unsubscribe(f"pioreactor/{self.unit}/{latest_exp}/+/$state")

        return

    def on_ready(self) -> None:
        self.flicker_led_response_okay()
        self.logger.notice(f"{self.unit} is online and ready.")  # type: ignore

        # we can delay this check until ready.
        self.check_state_of_jobs_on_machine()

    def on_disconnected(self) -> None:
        self.GPIO.cleanup(LED_PIN)
        self.GPIO.cleanup(BUTTON_PIN)
        set_gpio_availability(BUTTON_PIN, True)
        set_gpio_availability(LED_PIN, True)

    def led_on(self) -> None:
        self.GPIO.output(LED_PIN, self.GPIO.HIGH)

    def led_off(self) -> None:
        self.GPIO.output(LED_PIN, self.GPIO.LOW)

    def button_down_and_up(self, *args) -> None:
        # Warning: this might be called twice: See "Switch debounce" in https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/
        # don't put anything that is not idempotent in here.

        self.led_on()

        self.button_down = True

        while self.GPIO.input(BUTTON_PIN) == self.GPIO.HIGH:
            sleep(0.02)

        self.led_off()

        self.button_down = False

    def check_for_power_problems(self) -> None:
        """
        Note: `get_throttled` feature isn't available on the Rpi Zero

        Sourced from https://github.com/raspberrypi/linux/pull/2397
         and https://github.com/N2Github/Proje
        """

        def status_to_human_readable(status) -> str:
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
                "Suggestion: use a larger external power supply. See docs at: https://docs.pioreactor.com/user-guide/external-power"
            )
            return ". ".join(hr_status)

        def currently_throttling(status: int) -> int:
            return (status & 0x2) or (status & 0x1) or (status & 0x4)

        def non_ignorable_status(status: int) -> int:
            return (status & 0x1) or (status & 0x4)

        if whoami.is_testing_env():
            return

        with open("/sys/devices/platform/soc/soc:firmware/get_throttled") as file:
            status = int(file.read(), 16)

        if not currently_throttling(status):
            self.logger.debug("Power status okay.")
        else:
            self.logger.debug(f"Power status: {status_to_human_readable(status)}")

    def publish_self_statistics(self) -> None:
        import psutil

        disk_usage_percent = round(psutil.disk_usage("/").percent)
        cpu_usage_percent = round(
            (psutil.cpu_percent() + psutil.cpu_percent() + psutil.cpu_percent()) / 3
        )  # this is a noisy process, and we average it over a small window.
        memory_usage_percent = 100 - round(
            100 * psutil.virtual_memory().available / psutil.virtual_memory().total
        )

        cpu_temperature_celcius = utils.get_cpu_temperature()

        if disk_usage_percent <= 80:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            # TODO: add documentation to clear disk space.
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")
            self.flicker_led_with_error_code(error_codes.DISK_IS_ALMOST_FULL_ERROR_CODE)

        if cpu_usage_percent <= 75:
            self.logger.debug(f"CPU usage at {cpu_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU usage at {cpu_usage_percent}%.")

        if memory_usage_percent <= 60:
            self.logger.debug(f"Memory usage at {memory_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"Memory usage at {memory_usage_percent}%.")

        if cpu_temperature_celcius <= 70:
            self.logger.debug(f"CPU temperature at {cpu_temperature_celcius} ℃.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU temperature at {cpu_temperature_celcius} ℃.")

        self.computer_statistics = {
            "disk_usage_percent": disk_usage_percent,
            "cpu_usage_percent": cpu_usage_percent,
            "memory_usage_percent": memory_usage_percent,
            "cpu_temperature_celcius": cpu_temperature_celcius,
            "timestamp": current_utc_timestamp(),
        }

    def flicker_led_response_okay(self, *args) -> None:
        if self.led_in_use:
            return

        self.led_in_use = True

        for _ in range(4):

            self.led_on()
            sleep(0.14)
            self.led_off()
            sleep(0.14)
            self.led_on()
            sleep(0.14)
            self.led_off()
            sleep(0.45)

        self.led_in_use = False

    def flicker_led_with_error_code(self, error_code: int) -> None:
        if self.led_in_use:
            return

        self.led_in_use = True

        self.led_on()
        sleep(2.0)
        self.led_off()
        sleep(0.2)
        for _ in range(error_code):
            self.led_on()
            sleep(0.2)
            self.led_off()
            sleep(0.2)

        sleep(5)

        self.led_in_use = False

    def run_job_on_machine(self, msg: MQTTMessage) -> None:

        import subprocess
        from shlex import (
            quote,
        )  # https://docs.python.org/3/library/shlex.html#shlex.quote

        job_name = quote(msg.topic.split("/")[-1])
        payload = loads(msg.payload)

        # this is a performance hack and should be changed later...
        if job_name == "led_intensity":
            from pioreactor.actions.led_intensity import led_intensity, ALL_LED_CHANNELS

            state = {c: payload.get(c) for c in ALL_LED_CHANNELS if c in payload}

            exp = whoami._get_latest_experiment_name()

            for c in ALL_LED_CHANNELS:
                payload.pop(c, None)

            led_intensity(state, unit=self.unit, experiment=exp, **payload)

        elif job_name in ["add_media", "add_alt_media", "remove_waste"]:
            from pioreactor.actions.pump import add_media, add_alt_media, remove_waste

            # we use a thread here since we want to exit this callback without blocking it.
            # a blocked callback can disconnect from MQTT broker.
            from threading import Thread

            if job_name == "add_media":
                pump = add_media
            elif job_name == "add_alt_media":
                pump = add_alt_media
            elif job_name == "remove_waste":
                pump = remove_waste

            payload["config"] = config.get_config()  # techdebt
            exp = whoami._get_latest_experiment_name()
            t = Thread(target=pump, args=(self.unit, exp), kwargs=payload, daemon=True)
            t.start()

        else:
            prefix = ["nohup"]
            core_command = ["pio", "run", job_name]
            args: list[str] = sum(
                [
                    [f"--{quote(key).replace('_', '-')}", quote(str(value))]
                    for key, value in payload.items()
                ],
                [],
            )
            suffix = [">/dev/null", "2>&1", "&"]

            command = " ".join((prefix + core_command + args + suffix))

            self.logger.debug(f"Running `{command}` from monitor job.")

            subprocess.run(command, shell=True)

    def flicker_error_code_from_mqtt(self, message: MQTTMessage) -> None:
        payload = int(message.payload)
        self.flicker_led_with_error_code(payload)

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self.flicker_led_response_okay,
            f"pioreactor/{self.unit}/+/{self.job_name}/flicker_led_response_okay",
            qos=QOS.AT_LEAST_ONCE,
        )

        # jobs can publish to the following topic to flicker error codes
        self.subscribe_and_callback(
            self.flicker_error_code_from_mqtt,
            f"pioreactor/{self.unit}/+/{self.job_name}/flicker_led_with_error_code",
            qos=QOS.AT_LEAST_ONCE,
        )

        # one can also start jobs via MQTT, using the following topics.
        # The payload provided is a json dict of options for the command line invocation of the job.
        self.subscribe_and_callback(
            self.run_job_on_machine,
            [
                f"pioreactor/{self.unit}/+/run/+",
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/+/run/+",
            ],
            allow_retained=False,
        )


@click.command(name="monitor")
def click_monitor() -> None:
    """
    Monitor and report metadata on the unit.
    """
    import os

    os.nice(1)

    job = Monitor(unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    job.block_until_disconnected()
