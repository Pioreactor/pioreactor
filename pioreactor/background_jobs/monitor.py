# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from contextlib import suppress
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Callable
from typing import Optional

import click

from pioreactor import error_codes
from pioreactor import utils
from pioreactor import version
from pioreactor import whoami
from pioreactor.background_jobs.base import LongRunningBackgroundJob
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.config import config
from pioreactor.config import get_leader_hostname
from pioreactor.config import get_mqtt_address
from pioreactor.hardware import GPIOCHIP
from pioreactor.hardware import is_HAT_present
from pioreactor.hardware import PCB_BUTTON_PIN as BUTTON_PIN
from pioreactor.hardware import PCB_LED_PIN as LED_PIN
from pioreactor.hardware import TEMP
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from
from pioreactor.pubsub import QOS
from pioreactor.structs import Voltage
from pioreactor.types import MQTTMessage
from pioreactor.utils.networking import discover_workers_on_network
from pioreactor.utils.networking import get_ip
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime

if whoami.is_testing_env():
    from pioreactor.utils.mock import MockCallback
    from pioreactor.utils.mock import MockHandle


class classproperty(property):
    def __get__(self, obj, objtype=None):
        return self.fget(objtype)


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
     6. Checks for connection to leader



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

    @classproperty
    def MAX_TEMP_TO_SHUTDOWN(cls) -> float:
        is_20ml_v1 = (
            whoami.get_pioreactor_model() == "pioreactor_20ml" and whoami.get_pioreactor_version() == (1, 0)
        )
        return 66.0 if is_20ml_v1 else 85.0

    @classproperty
    def MAX_TEMP_TO_SHUTDOWN_IF_NO_TEMP_AUTOMATION(cls) -> float:
        return 65.0

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

        # previously I had pioreactor_version and model name here, but this starts before the webserver is online, and it
        # would crash this job.
        self.versions = {
            "app": pretty_version(version.software_version_info),
            "hat": pretty_version(version.hardware_version_info),
            "firmware": pretty_version(version.get_firmware_version()),
            "hat_serial": version.serial_number,
            "rpi_machine": version.rpi_version_info,
            "timestamp": current_utc_timestamp(),
            "ui": None,
        }

        self.logger.debug(f"Pioreactor software version: {self.versions['app']}")
        self.logger.debug(f"Raspberry Pi: {self.versions['rpi_machine']}")
        self.logger.debug(f"Pioreactor HAT version: {self.versions['hat']}")
        self.logger.debug(f"Pioreactor firmware version: {self.versions['firmware']}")
        self.logger.debug(f"Pioreactor HAT serial number: {self.versions['hat_serial']}")

        self.button_down = False

        try:
            # set up GPIO for accessing the button and changing the LED
            # if these fail, don't kill the entire job - sucks for onboarding.
            self._setup_GPIO()
        except Exception as e:
            self.logger.debug(e, exc_info=True)

        # set up a self check function to periodically check vitals and log them
        # we manually run a self_check outside of a thread first, as if there are
        # problems detected, we may want to block and not let the job continue.
        self.self_check_thread = RepeatedTimer(
            12 * 60 * 60, self.self_checks, job_name=self.job_name, run_immediately=True, logger=self.logger
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
            return

        def did_find_network() -> bool:
            ipv4 = get_ip()

            if ipv4 == "127.0.0.1" or ipv4 == "":
                # no connection? Sound the alarm.
                self.logger.warning("Unable to find a network...")
                self.flicker_led_with_error_code(error_codes.NO_NETWORK_CONNECTION)
                return False
            else:
                return True

        utils.boolean_retry(did_find_network, retries=3, sleep_for=2)
        self.ipv4 = get_ip()

        def get_mac_addresses(interface_type: str) -> str:
            """
            Finds all network interfaces of the given type (wireless or wired) and retrieves their MAC addresses.
            Returns a comma-separated string of MAC addresses.
            """
            net_path = Path("/sys/class/net")
            mac_addresses = []

            for iface_path in net_path.iterdir():
                if iface_path.is_dir():
                    try:
                        iface_type_path = iface_path / "type"
                        is_wireless = (iface_path / "wireless").exists()

                        if iface_type_path.exists():
                            iface_type = iface_type_path.read_text().strip()

                            # Collect MAC addresses for specified type
                            if interface_type == "wireless" and is_wireless:
                                mac_addresses.append((iface_path / "address").read_text().strip())
                            elif interface_type == "wired" and iface_type == "1" and not is_wireless:
                                mac_addresses.append((iface_path / "address").read_text().strip())
                    except (FileNotFoundError, ValueError):
                        continue

            return ", ".join(mac_addresses) if mac_addresses else "Not available"

        # Get MAC addresses for all wireless and wired interfaces
        self.wlan_mac_address = get_mac_addresses("wireless")
        self.eth_mac_address = get_mac_addresses("wired")

        self.logger.debug(f"IPv4 address: {self.ipv4}")
        self.logger.debug(f"WLAN MAC address: {self.wlan_mac_address}")
        self.logger.debug(f"Ethernet MAC address: {self.eth_mac_address}")

    def self_checks(self) -> None:
        self.button_down = False  # reset this.
        sleep(0 if whoami.is_testing_env() else 5)  # wait for other processes to catch up

        # check active network connection
        self.check_for_network()
        # report on CPU usage, memory, disk space
        self.check_and_publish_self_statistics()
        self.check_for_webserver()

        if whoami.am_I_leader():
            self.check_for_last_backup()
            self.check_for_correct_permissions()
            self.check_for_required_jobs_running()

        try:
            am_I_a_worker = whoami.am_I_a_worker()
        except Exception:
            # can error out due to a network failure
            am_I_a_worker = False

        if am_I_a_worker:
            # watch for undervoltage problems
            self.check_for_power_problems()
            # workers need a HAT
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
        try:
            r = get_from("localhost", "/unit_api/versions/ui")
            r.raise_for_status()
            ui_version = r.json()["version"]
        except HTTPException:
            self.set_state(self.LOST)
            self.logger.warning("Webserver isn't online.")
            self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
            ui_version = "Unknown"
        except Exception as e:
            self.set_state(self.LOST)
            self.logger.warning(e)
            self.flicker_led_with_error_code(error_codes.WEBSERVER_OFFLINE)
            ui_version = "Unknown"
        finally:
            self.set_versions({"ui": ui_version})
            self.logger.debug(f"Pioreactor UI version: {self.versions['ui']}")

    def check_for_required_jobs_running(self) -> None:
        # we put this in a while loop since if mqtt_to_db_streaming is not working, the warning is not saved to disk,
        # and the user may never a notification every N hours. So we just spam the user.
        sleep(5)  # give it a moment to start.
        while not utils.is_pio_job_running("mqtt_to_db_streaming"):
            self.logger.warning(
                "mqtt_to_db_streaming should be running on leader. Check `sudo systemctl status pioreactor_startup_run@mqtt_to_db_streaming.service`, or try restarting."
            )
            sleep(30)

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
                from pioreactor.utils.temps import TMP1075  # type: ignore
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
            # something is wrong - temperature_automation should have detected this, but didn't, so it must have failed / incorrectly cleaned up.
            # we're going to just shutdown to be safe.
            self.logger.error(
                f"Detected an extremely high temperature, {observed_tmp} ℃ on the heating PCB - shutting down for safety."
            )

            subprocess.call("sudo shutdown now --poweroff", shell=True)

        elif observed_tmp >= self.MAX_TEMP_TO_SHUTDOWN_IF_NO_TEMP_AUTOMATION and not utils.is_pio_job_running(
            "temperature_automation"
        ):
            # errant PWM?
            # false positive: small chance this is in an incubator?

            self.logger.error(
                f"Detected an extremely high temperature but heating is turned off, {observed_tmp} ℃ on the heating PCB - shutting down for safety."
            )

            subprocess.call("sudo shutdown now --poweroff", shell=True)

        self.logger.debug(f"Heating PCB temperature at {round(observed_tmp)} ℃.")

    def check_for_mqtt_connection_to_leader(self) -> None:
        while (not self.pub_client.is_connected()) or (not self.sub_client.is_connected()):
            self.logger.warning(
                f"""Not able to connect MQTT clients to leader.
1. Is the mqtt_adress={get_mqtt_address()} in configuration correct?
2. Is the Pioreactor leader online and responsive?
"""
            )  # remember, this doesn't get published to leader...
            self.flicker_led_with_error_code(error_codes.MQTT_CLIENT_NOT_CONNECTED_TO_LEADER)

            try:
                self.pub_client.disconnect()
                error_code_pc = (
                    self.pub_client.reconnect()
                )  # this may return a MQTT_ERR_SUCCESS, but that only means the CONNECT message is sent, still waiting for a CONNACK.
                self.pub_client.loop_start()
                self.logger.debug(f"{error_code_pc=}")
            except Exception as e:
                self.logger.debug(f"{e=}")

            try:
                self.sub_client.disconnect()
                error_code_sc = self.sub_client.reconnect()
                self.sub_client.loop_start()
                self.logger.debug(f"{error_code_sc=}")
            except Exception as e:
                self.logger.debug(f"{e=}")

            sleep(2)

            # self.set_state(self.LOST)

    def check_for_last_backup(self) -> None:
        with utils.local_persistent_storage("database_backups") as cache:
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

    def on_init_to_ready(self) -> None:
        if whoami.am_I_leader():
            Thread(target=self.announce_new_workers, daemon=True).start()

    def on_disconnected(self) -> None:
        import lgpio

        self.led_off()
        with suppress(AttributeError):
            self._button_callback.cancel()
            lgpio.gpiochip_close(self._handle)

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
        # don't bother checking if hat isn't present
        if not is_HAT_present():
            return

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
        import os

        # Disk usage percentage
        statvfs = os.statvfs("/")
        total_disk_space = statvfs.f_frsize * statvfs.f_blocks
        available_disk_space = statvfs.f_frsize * statvfs.f_bavail
        disk_usage_percent = round((1 - available_disk_space / total_disk_space) * 100)

        if disk_usage_percent <= 80:
            self.logger.debug(f"Disk space at {disk_usage_percent}%.")
        else:
            # TODO: add documentation to clear disk space.
            self.logger.warning(f"Disk space at {disk_usage_percent}%.")
            self.flicker_led_with_error_code(error_codes.DISK_IS_ALMOST_FULL)

        cpu_temperature_celcius = round(utils.get_cpu_temperature())
        if cpu_temperature_celcius <= 70:
            self.logger.debug(f"CPU temperature at {cpu_temperature_celcius} ℃.")
        else:
            # TODO: add documentation
            self.logger.warning(f"CPU temperature at {cpu_temperature_celcius} ℃.")
            self.flicker_led_with_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

        self.computer_statistics = {
            "disk_usage_percent": disk_usage_percent,
            "cpu_temperature_celcius": cpu_temperature_celcius,
            "timestamp": current_utc_timestamp(),
        }
        return

    def flicker_led_response_okay_and_publish_state(self, *args) -> None:
        self.flicker_led_response_okay()

    def _republish_state(self) -> None:
        self._publish_setting("state")

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

        self._republish_state()

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

    def watch_for_lost_state(self, state_message: MQTTMessage) -> None:
        unit = state_message.topic.split("/")[1]

        # ignore if leader is "lost"
        if (
            (state_message.payload.decode() == self.LOST)
            and (unit != self.unit)
            and (unit in get_workers_in_inventory())
        ):
            self.logger.warning(f"{unit} seems to be lost.")

    def announce_new_workers(self) -> None:
        sleep(10)  # wait for the web server to be available
        for worker in discover_workers_on_network():
            # not in current cluster, and not leader
            if (worker not in get_workers_in_inventory()) and (worker != get_leader_hostname()):
                self.logger.notice(  # type: ignore
                    f"Pioreactor worker, {worker}, is available to be added to your cluster."
                )

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

        if whoami.am_I_leader():
            self.subscribe_and_callback(
                self.watch_for_lost_state,
                "pioreactor/+/+/monitor/$state",
                allow_retained=False,
            )


@click.command(name="monitor")
def click_monitor() -> None:
    """
    Monitor and report metadata on the unit.
    """
    with Monitor(unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT) as job:
        job.block_until_disconnected()
