# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from json import loads
from threading import Thread
from time import sleep
from typing import Any
from typing import Callable
from typing import Optional

import click

from pioreactor import config
from pioreactor import error_codes
from pioreactor import utils
from pioreactor import version
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware import is_HAT_present
from pioreactor.hardware import PCB_BUTTON_PIN as BUTTON_PIN
from pioreactor.hardware import PCB_LED_PIN as LED_PIN
from pioreactor.hardware import TEMP
from pioreactor.mureq import get
from pioreactor.pubsub import QOS
from pioreactor.structs import Voltage
from pioreactor.types import MQTTMessage
from pioreactor.utils import retry
from pioreactor.utils.gpio_helpers import set_gpio_availability
from pioreactor.utils.networking import get_ip
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime


class Monitor(BackgroundJob):
    """
    This job starts at Rpi startup, and isn't connected to any experiment. It has the following roles:

     1. Reports metadata (voltage, CPU usage, etc.) about the Rpi / Pioreactor to the leader
     2. Controls the LED / Button interaction. Plus any additional callbacks to the button down/up.
     3. Correction after a restart
     4. Check database backup if leader
     5. Use the LED blinks to report error codes to the user, see error_codes module
        can also be invoked with the MQTT topic:
         pioreactor/{unit}/+/monitor/flicker_led_with_error_code   error_code as message
     6. Listens to MQTT for job to start, on the topic
         pioreactor/{unit}/$experiment/run/{job_name}   json-encoded args as message
     7. Checks for connection to leader


     TODO: start a watchdog job on all pioreactors (currently only on leader), and let it monitor the network activity.
     OR merge the watchdog with monitor


    Notes
    -------

    Use `Monitor.add_post_button_callback` and `Monitor.add_pre_button_callback` to change what the button can do. Ex:

        from pioreactor.background_jobs.monitor import  Monitor
        from pioreactor.actions.led_intensity import led_intensity

        def on(): # functions don't take any arguments, nothing is passed in
            led_intensity({'B': 20}, verbose=False, source_of_event="button", unit="demo", experiment="demo")

        def off(): # functions don't take any arguments, nothing is passed in
            led_intensity({'B': 0}, verbose=False, source_of_event="button", unit="demo", experiment="demo")

        Monitor.add_pre_button_callback(on)
        Monitor.add_post_button_callback(off)

    """

    MAX_TEMP_TO_SHUTDOWN = 66.0
    job_name = "monitor"
    published_settings = {
        "computer_statistics": {"datatype": "json", "settable": False},
        "button_down": {"datatype": "boolean", "settable": False},
        "versions": {"datatype": "json", "settable": False},
        "voltage_on_pwm_rail": {"datatype": "Voltage", "settable": False},
        "ipv4": {"datatype": "string", "settable": False},
    }
    computer_statistics: Optional[dict] = None
    led_in_use: bool = False
    _pre_button: list[Callable] = []
    _post_button: list[Callable] = []

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(unit=unit, experiment=experiment)

        def pretty_version(info: tuple) -> str:
            return ".".join((str(x) for x in info))

        # TODO: problem: these values aren't updated when software updates, only on monitor init. This makes them unreliable
        # Sol1: restart monitor after pio update app - but this is very heavy handed.
        # Sol2: pio update app republishes this data, OR publishes an event that Monitor listens to.
        #
        self.versions = {
            "software": pretty_version(version.software_version_info),
            "hat": pretty_version(version.hardware_version_info),
            "hat_serial": version.serial_number,
            "timestamp": current_utc_timestamp(),
        }

        self.logger.debug(
            f"Pioreactor software version: {pretty_version(version.software_version_info)}"
        )

        if whoami.am_I_active_worker():
            self.logger.debug(f"Pioreactor HAT version: {self.versions['hat']}")

            self.logger.debug(
                f"Pioreactor firmware version: {pretty_version(version.get_firmware_version())}"
            )

            self.logger.debug(f"Pioreactor HAT serial number: {self.versions['hat_serial']}")

        self.button_down = False
        # set up GPIO for accessing the button and changing the LED

        try:
            # if these fail, don't kill the entire job - sucks for onboarding.
            self._setup_GPIO()
            self.self_checks()
        except Exception as e:
            self.logger.debug(e, exc_info=True)

        # set up a self check function to periodically check vitals and log them
        # we manually run a self_check outside of a thread first, as if there are
        # problems detected, we may want to block and not let the job continue.
        self.self_check_thread = RepeatedTimer(
            4 * 60 * 60,
            self.self_checks,
            job_name=self.job_name,
            run_immediately=False,
        ).start()

        self.add_pre_button_callback(self.led_on)
        self.add_pre_button_callback(self._republish_state)
        self.add_post_button_callback(self.led_off)

        self.start_passive_listeners()

    @classmethod
    def add_pre_button_callback(cls, function: Callable):
        cls._pre_button.append(function)

    @classmethod
    def add_post_button_callback(cls, function: Callable):
        cls._post_button.append(function)

    def _setup_GPIO(self) -> None:
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
            retry(
                self.GPIO.add_event_detect,
                retries=3,
                delay=1.0,
                args=(BUTTON_PIN, self.GPIO.RISING),
                kwargs={"callback": self.button_down_and_up, "bouncetime": 100},
            )
        except RuntimeError:
            self.logger.warning("Failed to add button detect.")

    def check_for_network(self) -> None:
        if whoami.is_testing_env():
            self.ipv4 = "127.0.0.1"
        else:
            ipv4 = get_ip()
            while ipv4 == "127.0.0.1" or ipv4 is None:
                # no wifi connection? Sound the alarm.
                self.logger.warning("Unable to connect to network...")
                self.flicker_led_with_error_code(error_codes.NO_NETWORK_CONNECTION)
                ipv4 = get_ip()

            self.ipv4 = ipv4

        self.logger.debug(f"IPv4 address: {self.ipv4}")

    def self_checks(self) -> None:
        # check active network connection
        self.check_for_network()

        # watch for undervoltage problems
        self.check_for_power_problems()

        # report on CPU usage, memory, disk space
        self.check_and_publish_self_statistics()

        if whoami.am_I_leader():
            self.check_for_last_backup()
            sleep(0 if whoami.is_testing_env() else 10)  # wait for other processes to catch up
            self.check_for_required_jobs_running()
            self.check_for_webserver()

        if whoami.am_I_active_worker():
            self.check_for_HAT()
            # check the PCB temperature
            self.check_heater_pcb_temperature()

        if not whoami.am_I_leader():
            # check for MQTT connection to leader
            self.check_for_mqtt_connection_to_leader()

    def check_for_webserver(self):
        if whoami.is_testing_env():
            return

        attempt = 0
        retries = 5
        try:
            while attempt < retries:
                attempt += 1
                # Run the command 'systemctl is-active lighttpd' and capture the output
                result = subprocess.run(
                    ["systemctl", "is-active", "lighttpd"], capture_output=True, text=True
                )
                status = result.stdout.strip()

                # Check if the output is okay
                if status == "failed" or status == "inactive":
                    self.logger.error("lighttpd is not running. Check `systemctl status lighttpd`.")
                    self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
                elif status == "activating":
                    # try again
                    pass
                elif status == "active":
                    # okay
                    break
                else:
                    raise ValueError(status)
                sleep(1.0)
        except Exception as e:
            self.logger.debug(f"Error checking lighttpd status: {e}", exc_info=True)
            self.logger.error(f"Error checking lighttpd status: {e}")

        attempt = 0
        retries = 5
        try:
            while attempt < retries:
                attempt += 1
                # Run the command 'systemctl is-active huey' and capture the output
                result = subprocess.run(
                    ["systemctl", "is-active", "huey"], capture_output=True, text=True
                )
                status = result.stdout.strip()

                # Check if the output is okay
                if status == "failed" or status == "inactive":
                    self.logger.error("huey is not running. Check `systemctl status huey`.")
                    self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
                elif status == "activating":
                    # try again
                    pass
                elif status == "active":
                    # okay
                    break
                else:
                    raise ValueError(status)
                sleep(1.0)
        except Exception as e:
            self.logger.debug(f"Error checking huey status: {e}", exc_info=True)
            self.logger.error(f"Error checking huey status: {e}")

        attempt = 0
        retries = 5
        while attempt < retries:
            attempt += 1
            res = get("http://localhost")
            if res.ok:
                break
            sleep(1.0)
        else:
            self.logger.debug(f"Error pinging UI: {res.status}")
            self.logger.error(f"Error pinging UI: {res.status}")
            self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)

    def check_for_required_jobs_running(self):
        if not all(utils.is_pio_job_running(["watchdog", "mqtt_to_db_streaming"])):
            self.logger.debug(
                "watchdog and mqtt_to_db_streaming should be running on leader. Double check."
            )

    def check_for_HAT(self) -> None:
        if not is_HAT_present():
            self.logger.warning("HAT is not detected.")

    def check_heater_pcb_temperature(self) -> None:
        """
        Originally from #220
        """
        if whoami.is_testing_env():
            from pioreactor.utils.mock import MockTMP1075 as TMP1075
        else:
            try:
                from TMP1075 import TMP1075  # type: ignore
            except ImportError:
                # leader-only is a worker?
                self.logger.warning(
                    f"{self.unit} doesn't have TMP1075 software installed, but is acting as a worker."
                )
                return

        try:
            tmp_driver = TMP1075(address=TEMP)
        except ValueError:
            # No PCB detected using i2c - fine to exit.
            self.logger.warning("Heater PCB is not detected.")
            return

        observed_tmp = tmp_driver.get_temperature()

        if observed_tmp >= self.MAX_TEMP_TO_SHUTDOWN:
            # something is wrong - temperature_control should have detected this, but didn't, so it must have failed / incorrectly cleaned up.
            # we're going to just shutdown to be safe.
            self.logger.error(
                f"Detected an extremely high temperature, {observed_tmp} ℃ on the heating PCB - shutting down for safety."
            )

            subprocess.call("sudo shutdown now --poweroff", shell=True)
        self.logger.debug(f"Heating PCB temperature at {round(observed_tmp)} ℃.")

    def check_for_mqtt_connection_to_leader(self) -> None:
        while (not self.pub_client.is_connected()) or (not self.sub_client.is_connected()):
            self.logger.warning(
                f"""Not able to connect MQTT clients to leader.
1. Is the leader, {config.leader_hostname} at {config.leader_address}, in config.ini correct?
2. Is the Pioreactor leader online and responsive?
"""
            )  # remember, this doesn't get published to leader...

            self.set_state(self.LOST)
            self.flicker_led_with_error_code(error_codes.MQTT_CLIENT_NOT_CONNECTED_TO_LEADER)

            try:
                self.pub_client.reconnect()
            except Exception:
                pass
            try:
                self.sub_client.reconnect()
            except Exception:
                pass

    def check_for_last_backup(self) -> None:
        with utils.local_persistant_storage("database_backups") as cache:
            if cache.get("latest_backup_timestamp"):
                latest_backup_at = to_datetime(cache["latest_backup_timestamp"])

                if (current_utc_datetime() - latest_backup_at).days > 30:
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
            if (msg.payload.decode() in (self.READY, self.INIT, self.SLEEPING)) and (
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

        self.button_down = True

        for pre_function in self._pre_button:
            try:
                pre_function()
            except Exception:
                self.logger.debug(f"Error in pre_function={pre_function.__name__}.", exc_info=True)

        while self.GPIO.input(BUTTON_PIN) == self.GPIO.HIGH:
            sleep(0.02)

        for post_function in self._post_button:
            try:
                post_function()
            except Exception:
                self.logger.debug(
                    f"Error in post_function={post_function.__name__}.", exc_info=True
                )

        self.button_down = False

    def rpi_is_having_power_problems(self) -> tuple[bool, float]:
        from pioreactor.utils.rpi_bad_power import new_under_voltage
        from pioreactor.hardware import voltage_in_aux

        voltage_read = voltage_in_aux(precision=0.05)
        under_voltage_flag = new_under_voltage()

        under_voltage_status = under_voltage_flag.get() if under_voltage_flag else None

        if voltage_read <= 4.80 and (under_voltage_status is None or under_voltage_status):
            return True, voltage_read
        else:
            return False, voltage_read

    def check_for_power_problems(self) -> None:
        is_rpi_having_power_probems, voltage = self.rpi_is_having_power_problems()
        self.logger.debug(f"PWM power supply at ~{voltage:.2f}V.")
        self.voltage_on_pwm_rail = Voltage(
            voltage=round(voltage, 2), timestamp=current_utc_datetime()
        )
        if is_rpi_having_power_probems:
            self.logger.warning(
                f"Low-voltage detected on rail. PWM power supply at {voltage:.1f}V. Suggestion: use a better power supply or an AUX power. See docs at: https://docs.pioreactor.com/user-guide/external-power"
            )
            self.flicker_led_with_error_code(error_codes.VOLTAGE_PROBLEM)
        else:
            self.logger.debug("Power status okay.")

    def check_and_publish_self_statistics(self) -> None:
        import psutil  # type: ignore

        disk_usage_percent = round(psutil.disk_usage("/").percent)
        if disk_usage_percent <= 80:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            # TODO: add documentation to clear disk space.
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")
            self.flicker_led_with_error_code(error_codes.DISK_IS_ALMOST_FULL)

        cpu_usage_percent = round(
            (psutil.cpu_percent() + psutil.cpu_percent() + psutil.cpu_percent()) / 3
        )  # this is a noisy process, and we average it over a small window.
        if cpu_usage_percent <= 85:
            self.logger.debug(f"CPU usage at {cpu_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU usage at {cpu_usage_percent}%.")

        memory_usage_percent = 100 - round(
            100 * psutil.virtual_memory().available / psutil.virtual_memory().total
        )
        if memory_usage_percent <= 75:
            self.logger.debug(f"Memory usage at {memory_usage_percent}%.")
        else:
            # TODO: add documentation
            self.logger.warning(f"Memory usage at {memory_usage_percent}%.")

        cpu_temperature_celcius = round(utils.get_cpu_temperature())
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
        return

    def flicker_led_response_okay_and_publish_state(self, *args) -> None:
        # force the job to publish it's state, so that users can use this to "reset" state.
        self.flicker_led_response_okay()
        self._republish_state()

    def _republish_state(self) -> None:
        self._publish_attr("state")

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
        sleep(0.25)
        for _ in range(error_code):
            self.led_on()
            sleep(0.25)
            self.led_off()
            sleep(0.25)

        sleep(5)

        self.led_in_use = False

    def run_job_on_machine(self, msg: MQTTMessage) -> None:
        """
        Listens to messages on pioreactor/{self.unit}/+/run/job_name

        Payload should look like:
        {
          "options": {
            "option_A": "value1",
            "option_B": "value2"
            "flag": None
          },
          "args": ["arg1", "arg2"]
        }


        effectively runs:
        > pio run job_name arg1 arg2 --option-A value1 --option-B value2 --flag

        """

        # we use a thread here since we want to exit this callback without blocking it.
        # a blocked callback can disconnect from MQTT broker, prevent other callbacks, etc.

        job_name = msg.topic.split("/")[-1]
        payload = loads(msg.payload) if msg.payload else {"options": {}, "args": []}

        if "options" not in payload:
            self.logger.debug(
                "`options` key missing from payload. You should provide an empty dictionary."
            )
        options = payload.get("options", {})

        if "args" not in payload:
            self.logger.debug("`args` key missing from payload. You should provide an empty list.")

        args = payload.get("args", [])

        # this is a performance hack and should be changed later...
        if job_name == "led_intensity":
            from pioreactor.actions.led_intensity import led_intensity, ALL_LED_CHANNELS

            state = {ch: options.pop(ch) for ch in ALL_LED_CHANNELS if ch in options}
            options["pubsub_client"] = self.pub_client
            options["unit"] = self.unit
            options["experiment"] = whoami._get_latest_experiment_name()  # techdebt
            Thread(
                target=led_intensity,
                args=(state,),
                kwargs=options,
            ).start()

        elif job_name in (
            "add_media",
            "add_alt_media",
            "remove_waste",
            "circulate_media",
            "circulate_alt_media",
        ):
            from pioreactor.actions import pump as pump_actions

            pump_action = getattr(pump_actions, job_name)

            options["unit"] = self.unit
            options["experiment"] = whoami._get_latest_experiment_name()  # techdebt
            options["config"] = config.get_config()  # techdebt
            Thread(target=pump_action, kwargs=options, daemon=True).start()

        else:
            command = self._job_options_and_args_to_shell_command(job_name, args, options)

            self.logger.debug(f"Running `{command}` from monitor job.")

            Thread(
                target=subprocess.run,
                args=(command,),
                kwargs={"shell": True, "start_new_session": True},
                daemon=True,
            ).start()

    @staticmethod
    def _job_options_and_args_to_shell_command(
        job_name: str, args: list[str], options: dict[str, Any]
    ) -> str:
        from shlex import join  # https://docs.python.org/3/library/shlex.html#shlex.quote

        prefix = "nohup"

        core_command = ["pio", "run", job_name]

        list_of_options: list[str] = []
        for option, value in options.items():
            list_of_options.append(f"--{option.replace('_', '-')}")
            if value is not None:
                # this handles flag arguments, like --dry-run
                list_of_options.append(str(value))

        suffix = ">/dev/null 2>&1 &"

        # shell-escaped to protect against injection vulnerabilities, see join docs
        # we don't escape the suffix.
        command = prefix + " " + join(core_command + args + list_of_options) + " " + suffix

        return command

    def flicker_error_code_from_mqtt(self, message: MQTTMessage) -> None:
        if self.led_in_use:
            return

        error_code = int(message.payload)
        Thread(target=self.flicker_led_with_error_code, args=(error_code,), daemon=True).start()

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self.flicker_led_response_okay_and_publish_state,
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
    job = Monitor(unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    job.block_until_disconnected()
