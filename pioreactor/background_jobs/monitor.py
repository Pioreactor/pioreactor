# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from contextlib import suppress
from shlex import join
from shlex import quote
from threading import Thread
from time import sleep
from typing import Any
from typing import Callable
from typing import Optional

import click
from msgspec.json import decode as loads

from pioreactor import error_codes
from pioreactor import utils
from pioreactor import version
from pioreactor import whoami
from pioreactor.background_jobs.base import LongRunningBackgroundJob
from pioreactor.config import config
from pioreactor.config import get_config
from pioreactor.config import get_mqtt_address
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.hardware import GPIOCHIP
from pioreactor.hardware import is_HAT_present
from pioreactor.hardware import PCB_BUTTON_PIN as BUTTON_PIN
from pioreactor.hardware import PCB_LED_PIN as LED_PIN
from pioreactor.hardware import TEMP
from pioreactor.pubsub import get_from_leader
from pioreactor.pubsub import QOS
from pioreactor.structs import Voltage
from pioreactor.types import MQTTMessage
from pioreactor.utils.gpio_helpers import set_gpio_availability
from pioreactor.utils.networking import get_ip
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime

if whoami.is_testing_env():
    from pioreactor.utils.mock import MockCallback
    from pioreactor.utils.mock import MockHandle


class Monitor(LongRunningBackgroundJob):
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

    if whoami.get_pioreactor_version() == (1, 0):
        # made from PLA
        MAX_TEMP_TO_SHUTDOWN = 66.0
    elif whoami.get_pioreactor_version() >= (1, 1):
        # made from PC-CF
        MAX_TEMP_TO_SHUTDOWN = 85.0  # risk damaging PCB components

    job_name = "monitor"
    published_settings = {
        "computer_statistics": {"datatype": "json", "settable": False},
        "button_down": {"datatype": "boolean", "settable": False},
        "versions": {"datatype": "json", "settable": True},
        "voltage_on_pwm_rail": {"datatype": "Voltage", "settable": False},
        "ipv4": {"datatype": "string", "settable": False},
        "wlan_mac_address": {"datatype": "string", "settable": False},
        "eth_mac_address": {"datatype": "string", "settable": False},
    }
    computer_statistics: Optional[dict] = None
    led_in_use: bool = False
    _pre_button: list[Callable] = []
    _post_button: list[Callable] = []

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(unit=unit, experiment=experiment)

        def pretty_version(info: tuple) -> str:
            return ".".join((str(x) for x in info))

        self.versions = {
            "app": pretty_version(version.software_version_info),
            "hat": pretty_version(version.hardware_version_info),
            "firmware": pretty_version(version.get_firmware_version()),
            "hat_serial": version.serial_number,
            "rpi_machine": version.rpi_version_info,
            "timestamp": current_utc_timestamp(),
            "pioreactor_version": version.tuple_to_text(whoami.get_pioreactor_version()),
            "pioreactor_model": whoami.get_pioreactor_model(),
        }

        self.logger.debug(f"Pioreactor software version: {self.versions['app']}")
        self.logger.debug(f"Raspberry Pi: {self.versions['rpi_machine']}")
        self.logger.debug(f"Pioreactor HAT version: {self.versions['hat']}")
        self.logger.debug(f"Pioreactor firmware version: {self.versions['firmware']}")
        self.logger.debug(f"Pioreactor HAT serial number: {self.versions['hat_serial']}")
        self.logger.debug(
            f"Pioreactor: {self.versions['pioreactor_model']} v{self.versions['pioreactor_version']}"
        )

        self.button_down = False
        # set up GPIO for accessing the button and changing the LED

        try:
            # if these fail, don't kill the entire job - sucks for onboarding.
            self._setup_GPIO()
        except Exception as e:
            self.logger.debug(e, exc_info=True)

        try:
            # if these fail, don't kill the entire job - sucks for onboarding.
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

        self.add_pre_button_callback(self._republish_state)
        self.add_pre_button_callback(self.led_on)
        self.add_post_button_callback(self.led_off)

        self.start_passive_listeners()

    @classmethod
    def add_pre_button_callback(cls, function: Callable) -> None:
        cls._pre_button.append(function)

    @classmethod
    def add_post_button_callback(cls, function: Callable) -> None:
        cls._post_button.append(function)

    def _setup_GPIO(self) -> None:
        import lgpio

        set_gpio_availability(BUTTON_PIN, False)
        set_gpio_availability(LED_PIN, False)

        if not whoami.is_testing_env():
            self._handle = lgpio.gpiochip_open(GPIOCHIP)

            # Set LED_PIN as output and initialize to low
            lgpio.gpio_claim_output(self._handle, LED_PIN)
            lgpio.gpio_write(self._handle, LED_PIN, 0)

            # Set BUTTON_PIN as input with no pull-up
            lgpio.gpio_claim_input(self._handle, BUTTON_PIN, lgpio.SET_PULL_DOWN)

            lgpio.gpio_claim_alert(self._handle, BUTTON_PIN, lgpio.BOTH_EDGES, lgpio.SET_PULL_DOWN)

            self._button_callback = lgpio.callback(
                self._handle, BUTTON_PIN, lgpio.BOTH_EDGES, self.button_down_and_up
            )
        else:
            self._button_callback = MockCallback()
            self._handle = MockHandle()

    def check_for_network(self) -> None:
        if whoami.is_testing_env():
            self.ipv4 = "127.0.0.1"
            self.wlan_mac_address = "d8:3a:dd:61:01:59"
            self.eth_mac_address = "d8:3a:dd:61:01:60"
        else:
            ipv4 = get_ip()
            while ipv4 == "127.0.0.1" or ipv4 is None:
                # no connection? Sound the alarm.
                self.logger.warning("Unable to connect to network...")
                self.flicker_led_with_error_code(error_codes.NO_NETWORK_CONNECTION)
                sleep(1)
                ipv4 = get_ip()

            self.ipv4 = ipv4

            try:
                with open("/sys/class/net/wlan0/address", "r") as f:
                    self.wlan_mac_address = f.read().strip()
            except FileNotFoundError:
                self.wlan_mac_address = "Not available"

            try:
                with open("/sys/class/net/eth0/address", "r") as f:
                    self.eth_mac_address = f.read().strip()
            except FileNotFoundError:
                self.eth_mac_address = "Not available"

        self.logger.debug(f"IPv4 address: {self.ipv4}")
        self.logger.debug(f"WLAN MAC address: {self.wlan_mac_address}")
        self.logger.debug(f"Ethernet MAC address: {self.eth_mac_address}")

    def self_checks(self) -> None:
        # check active network connection
        self.check_for_network()

        # watch for undervoltage problems
        self.check_for_power_problems()

        # report on CPU usage, memory, disk space
        self.check_and_publish_self_statistics()

        if whoami.am_I_leader():
            self.check_for_last_backup()
            sleep(0 if whoami.is_testing_env() else 5)  # wait for other processes to catch up
            self.check_for_correct_permissions()
            self.check_for_webserver()
            self.check_for_required_jobs_running()

        if whoami.am_I_active_worker():
            self.check_for_HAT()
            # check the PCB temperature
            self.check_heater_pcb_temperature()

        if not whoami.am_I_leader():
            # check for MQTT connection to leader
            self.check_for_mqtt_connection_to_leader()

    def check_for_correct_permissions(self) -> None:
        if whoami.is_testing_env():
            return

        from pathlib import Path

        storage_path = Path(config.get("storage", "database")).parent

        for file in [
            storage_path / "pioreactor.sqlite",
            # shm and wal sometimes aren't present at when monitor starts - removed too many false positives
            # storage_path / "pioreactor.sqlite-shm",
            # storage_path / "pioreactor.sqlite-wal",
        ]:
            if file.exists() and (file.owner() != "pioreactor" or file.group() != "www-data"):
                self.logger.warning(
                    f"Pioreactor sqlite database file {file} has the wrong permissions / does not exist."
                )
                break

        return

    def check_for_webserver(self) -> None:
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

                # Check stderr if stdout is empty
                if not status:
                    status = result.stderr.strip()

                # Handle case where status is still empty
                if not status:
                    raise ValueError("No output from systemctl command")

                # Check if the output is okay
                if status == "failed" or status == "inactive" or status == "deactivating":
                    self.logger.error("lighttpd is not running. Check `systemctl status lighttpd`.")
                    self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
                elif status == "activating" or status == "reloading":
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
                result = subprocess.run(["systemctl", "is-active", "huey"], capture_output=True, text=True)
                status = result.stdout.strip()

                # Check stderr if stdout is empty
                if not status:
                    status = result.stderr.strip()

                # Handle case where status is still empty
                if not status:
                    raise ValueError("No output from systemctl command")

                # Check if the output is okay
                if status == "failed" or status == "inactive" or status == "deactivating":
                    self.logger.error("huey is not running. Check `systemctl status huey`.")
                    self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
                elif status == "activating" or status == "reloading":
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
            res = get_from_leader("/api/experiments/latest")
            if res.ok:
                break
            sleep(1.0)
        else:
            self.logger.debug(f"Error pinging UI: {res.status_code}")
            self.logger.error(f"Error pinging UI: {res.status_code}")
            self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)

    def check_for_required_jobs_running(self) -> None:
        if not all(utils.is_pio_job_running(["watchdog", "mqtt_to_db_streaming"])):
            self.logger.warning(
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
                self.logger.debug(
                    f"{self.unit} doesn't have TMP1075 software installed, but is acting as a worker."
                )
                return

        try:
            tmp_driver = TMP1075(address=TEMP)
        except ValueError:
            # No PCB detected using i2c - fine to exit.
            self.logger.debug("Heater PCB is not detected.")
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
            try:
                error_code_pc = self.pub_client.reconnect()
                self.logger.debug(f"{error_code_pc=}")
            except Exception:
                pass
            try:
                error_code_sc = self.sub_client.reconnect()
                self.logger.debug(f"{error_code_sc=}")
            except Exception:
                pass

            self.logger.warning(
                f"""Not able to connect MQTT clients to leader.
1. Is the mqtt_adress={get_mqtt_address()}, in config.ini correct?
2. Is the Pioreactor leader online and responsive?
"""
            )  # remember, this doesn't get published to leader...

            # self.set_state(self.LOST)
            self.flicker_led_with_error_code(error_codes.MQTT_CLIENT_NOT_CONNECTED_TO_LEADER)

    def check_for_last_backup(self) -> None:
        with utils.local_persistant_storage("database_backups") as cache:
            if cache.get("latest_backup_timestamp"):
                latest_backup_at = to_datetime(cache["latest_backup_timestamp"])

                if (current_utc_datetime() - latest_backup_at).days > 30:
                    self.logger.warning(
                        "Database hasn't been backed up in over 30 days. Try running `pio run backup_database` between experiments."
                    )

    def on_ready(self) -> None:
        self.flicker_led_response_okay()
        self.logger.notice(f"{self.unit} is online and ready.")  # type: ignore

        # we can delay this check until ready.

    def on_disconnected(self) -> None:
        import lgpio

        self.led_off()
        with suppress(AttributeError):
            self._button_callback.cancel()
            lgpio.gpiochip_close(self._handle)

        set_gpio_availability(BUTTON_PIN, True)
        set_gpio_availability(LED_PIN, True)

    def led_on(self) -> None:
        import lgpio

        if not whoami.is_testing_env():
            lgpio.gpio_write(self._handle, LED_PIN, 1)

    def led_off(self) -> None:
        import lgpio

        if not whoami.is_testing_env():
            lgpio.gpio_write(self._handle, LED_PIN, 0)

    def button_down_and_up(self, chip, gpio, level, tick) -> None:
        # Warning: this might be called twice
        # don't put anything that is not idempotent in here.
        if level == 1:
            self.button_down = True

            for pre_function in self._pre_button:
                try:
                    pre_function()
                except Exception:
                    self.logger.debug(f"Error in pre_function={pre_function.__name__}.", exc_info=True)

        elif level == 0:
            self.button_down = False

            for post_function in self._post_button:
                try:
                    post_function()
                except Exception:
                    self.logger.debug(f"Error in post_function={post_function.__name__}.", exc_info=True)

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
        self.voltage_on_pwm_rail = Voltage(voltage=round(voltage, 2), timestamp=current_utc_datetime())
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
            self.flicker_led_with_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

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

        # we use a thread below since we want to exit this callback without blocking it.
        # a blocked callback can disconnect from MQTT broker, prevent other callbacks, etc.
        # TODO: we should this entire code into a thread...

        topic_parts = msg.topic.split("/")

        job_name = topic_parts[-1]
        experiment = topic_parts[2]

        if experiment != whoami.UNIVERSAL_EXPERIMENT:
            # we put this into two if statements to minimize chances we have to fetch data.
            try:
                assigned_experiment = whoami._get_assigned_experiment_name(self.unit)
            except NotAssignedAnExperimentError:
                assigned_experiment = whoami.NO_EXPERIMENT

            # make sure I'm assigned to the correct experiment
            if experiment != assigned_experiment:
                return
        else:
            assigned_experiment = None

        payload = loads(msg.payload) if msg.payload else {"options": {}, "args": []}

        options = payload.get("options", {})

        args = payload.get("args", [])

        # this is a performance hack and should be changed later...
        if job_name == "led_intensity":
            # TODO: this needs to check if active / assigned
            # the below would work, but is very slow for a callback
            # putting it in led_intensity makes everything else slow (ex: od_reading)
            # if not whoami.is_active(self.unit):
            #    return

            from pioreactor.actions.led_intensity import led_intensity, ALL_LED_CHANNELS

            state = {ch: options.pop(ch) for ch in ALL_LED_CHANNELS if ch in options}
            options["pubsub_client"] = self.pub_client
            options["unit"] = self.unit
            options["experiment"] = experiment  # techdebt
            options.pop("job_source", "")  # techdebt, led_intensity doesn't use job_source
            Thread(
                target=utils.boolean_retry,
                args=(led_intensity, (state,), options),
                kwargs={"sleep_for": 0.4, "retries": 5},
            ).start()

        elif job_name in {
            "add_media",
            "add_alt_media",
            "remove_waste",
            "circulate_media",
            "circulate_alt_media",
        }:
            # is_active is checked in the lifecycle block

            from pioreactor.actions import pump as pump_actions

            pump_action = getattr(pump_actions, job_name)

            options["unit"] = self.unit
            options["experiment"] = experiment  # techdebt
            options["config"] = get_config()  # techdebt
            Thread(target=pump_action, kwargs=options, daemon=True).start()

        else:
            command = self._job_options_and_args_to_shell_command(
                job_name, assigned_experiment, args, options
            )
            Thread(
                target=subprocess.run,
                args=(command,),
                kwargs={"shell": True, "start_new_session": True},
                daemon=True,
            ).start()
            self.logger.debug(f"Running `{command}` from monitor job.")

    @staticmethod
    def _job_options_and_args_to_shell_command(
        job_name: str, experiment: Optional[str], args: list[str], options: dict[str, Any]
    ) -> str:
        core_command = ["pio", "run", job_name]

        # job source could be experiment_profile, but defaults to user
        # we actually can skip another API request by reusing the assigned experiment above...
        env = f'JOB_SOURCE={quote(options.pop("job_source", "user"))}'
        if experiment:
            env += f" EXPERIMENT={quote(experiment)}"

        list_of_options: list[str] = []
        for option, value in options.items():
            list_of_options.append(f"--{option.replace('_', '-')}")
            if value is not None:
                # this handles flag arguments, like --dry-run
                list_of_options.append(str(value))

        # shell-escaped to protect against injection vulnerabilities, see join docs
        # we don't escape the suffix.
        return env + " " + join(["nohup"] + core_command + args + list_of_options) + " >/dev/null 2>&1 &"

    def flicker_error_code_from_mqtt(self, message: MQTTMessage) -> None:
        if self.led_in_use:
            return

        error_code = int(message.payload)
        Thread(target=self.flicker_led_with_error_code, args=(error_code,), daemon=True).start()

    def set_versions(self, data: dict):
        # first remove any extra keys
        for key in data:
            if key not in self.versions:
                data.pop(key)

        self.versions = self.versions | data

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
