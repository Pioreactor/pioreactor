# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the temperature automation.


To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/temperture_control/temperature_automation/set`
message: a json object with required keyword argument. Specify the new automation with name `"temperature_automation"`.

"""
import json, signal, time

import click

from pioreactor.pubsub import QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.logging import create_logger
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer, current_utc_time
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.utils.pwm import PWM


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class TemperatureController(BackgroundJob):

    automations = {}

    editable_settings = ["temperature_automation", "temperature"]

    def __init__(self, temperature_automation, unit=None, experiment=None, **kwargs):
        super(TemperatureController, self).__init__(
            job_name="temperature_control", unit=unit, experiment=experiment
        )

        self.temperature_automation = temperature_automation

        self.temperature_automation_job = self.automations[self.temperature_automation](
            unit=self.unit, experiment=self.experiment, parent=self, **kwargs
        )

        self.ema = ExponentialMovingAverage(0.0)

        try:
            from TMP1075 import TMP1075
        except (NotImplementedError, ModuleNotFoundError):
            self.logger.debug("TMP1075 not available; using MockTMP1075")
            from pioreactor.utils.mock import MockTMP1075 as TMP1075

        try:
            self.tmp_driver = TMP1075()
        except ValueError as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(
                "Is the Heating PCB attached to the RaspberryPi? Unable to find I²C for temperature driver."
            )
            raise IOError(
                "Is the Heating PCB attached to the RaspberryPi? Unable to find I²C for temperature driver."
            )

        self.record_pcb_temperature_timer = RepeatedTimer(
            10, self.read_pcb_temperature, run_immediately=True
        )
        self.record_pcb_temperature_timer.start()

        self.publish_temperature_timer = RepeatedTimer(
            10 * 60, self.evaluate_and_publish_temperature
        )
        self.publish_temperature_timer.start()

        self.pwm = self.setup_pwm()
        self._update_heater(0)

    def set_temperature_automation(self, new_temperature_automation_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.temperature_automation_job.set_state("init")
        # self.temperature_automation_job.set_state("ready")
        # [ ] write tests
        # OR should just bail...
        algo_init = json.loads(new_temperature_automation_json)
        new_automation = algo_init["temperature_automation"]
        try:
            self.temperature_automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            time.sleep(1)
            self.set_temperature_automation(new_temperature_automation_json)

        try:
            self.temperature_automation_job = self.automations[new_automation](
                unit=self.unit, experiment=self.experiment, parent=self, **algo_init
            )
            self.temperature_automation = algo_init["temperature_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def turn_off_heater(self):
        self._update_heater(0)
        self.pwm.stop()
        self.pwm.cleanup()
        # we re-instantiate it as some other process may have messed with the channel.
        self.pwm = self.setup_pwm()
        self._update_heater(0)
        self.pwm.stop()

    def update_heater(self, new_duty_cycle):
        """
        Update heater's duty cycle. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        if not self.pwm.is_locked():
            self._update_heater(new_duty_cycle)
            return True
        else:
            return False

    ##### internal and private methods ########

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        # TODO: this could move to the base class
        for attr in self.editable_settings:
            if attr in ["state", "temperature"]:
                continue
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.EXACTLY_ONCE,
            )

    def _update_heater(self, new_duty_cycle):
        self.heater_duty_cycle = clamp(0, round(float(new_duty_cycle), 2), 100)
        self.pwm.change_duty_cycle(self.heater_duty_cycle)

    def _check_if_exceeds_max_temp(self, temp):
        MAX_TEMP_TO_DISABLE_HEATING = 55.0
        MAX_TEMP_TO_SHUTDOWN = 58.0

        if temp > MAX_TEMP_TO_DISABLE_HEATING:
            self.logger.warning(
                f"Temperature of heating surface has exceeded {MAX_TEMP_TO_DISABLE_HEATING}℃. This is beyond our recommendations. The heating PWM channel will be forced to 0. Take caution when touching the heating surface and wetware."
            )

            self.turn_off_heater()

        elif temp > MAX_TEMP_TO_SHUTDOWN:
            self.logger.warning(
                f"Temperature of heating surface has exceeded {MAX_TEMP_TO_SHUTDOWN}℃. This is beyond our recommendations. Shutting down to prevent further problems. Take caution when touching the heating surface and wetware."
            )

            from subprocess import call

            call("sudo shutdown --poweroff", shell=True)

    def on_sleeping(self):
        self.temperature_automation_job.set_state(self.SLEEPING)

    def on_sleeping_to_ready(self):
        self.temperature_automation_job.set_state(self.READY)

    def on_disconnect(self):
        try:
            self.temperature_automation_job.set_state(self.DISCONNECTED)
        except AttributeError:
            # if disconnect is called right after starting, temperature_automation_job isn't instantiated
            # time.sleep(1)
            # self.on_disconnect()
            # return
            pass

        self.clear_mqtt_cache()
        self._update_heater(0)
        self.pwm.stop()
        self.pwm.cleanup()

    def setup_pwm(self):
        hertz = 4
        pin = PWM_TO_PIN[config.getint("PWM_reverse", "heating")]
        pwm = PWM(pin, hertz)
        pwm.start(0)
        return pwm

    def evaluate_and_publish_temperature(self):
        """
        1. turn off heater and lock it
        2. start recording temperatures from the sensor
        3. After collected M samples, pass to a model to approx temp
        4. assign temp to publish to .../temperature
        5. return heater to previous DC value and unlock heater
        """

        assert not self.pwm.is_locked()

        with self.pwm.lock_temporarily():

            previous_heater_dc = self.heater_duty_cycle
            self._update_heater(0)

            N_sample_points = 25
            time_between_samples = 10
            temp_readings_after_shutoff = []  # TODO: make this a dict
            timestamp = current_utc_time()  # TODO: what should timestamp represent???

            while len(temp_readings_after_shutoff) < N_sample_points:
                temp_readings_after_shutoff.append(self.read_pcb_temperature())
                time.sleep(time_between_samples)

            self.logger.debug(temp_readings_after_shutoff)
            approximated_temperature = self.approximate_temperature(
                temp_readings_after_shutoff
            )
            self.logger.debug(approximated_temperature)

            # maybe check for sane values first
            self.temperature = {
                "temperature": approximated_temperature,
                "timestamp": timestamp,
            }

            self._update_heater(previous_heater_dc)

    def approximate_temperature(self, list_of_temps):
        # check if we are using silent, if so, we can short this and return single value?s

        return sum(list_of_temps) / len(list_of_temps)

    def read_pcb_temperature(self):
        """
        Read the current temperature from our sensor, in Celsius

        TODO: this should raise some error if I'm not able to find the I2C address -> likely
              the heating PCB is not connected.
        """
        pcb_temp = self.tmp_driver.get_temperature()
        self.logger.debug(f"PCB Temp {pcb_temp}")
        self._check_if_exceeds_max_temp(pcb_temp)
        return pcb_temp


def run(automation=None, duration=None, skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["skip_first_run"] = skip_first_run

        controller = TemperatureController(automation, **kwargs)  # noqa: F841

        signal.pause()

    except Exception as e:
        logger = create_logger("temperature_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


@click.command(name="temperature_control")
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system",
    show_default=True,
)
@click.option("--target-temperature", default=None, type=float)
@click.option(
    "--target-growth-rate", default=None, type=float, help="used in PIDMorbidostat only"
)
@click.option(
    "--duration",
    default=1 / config.getfloat("temperature_config.sampling", "samples_per_second"),
    help="in seconds",
)
@click.option(
    "--skip-first-run",
    is_flag=True,
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
def click_temperature_control(
    automation, target_temperature, duration, target_growth_rate, skip_first_run
):
    """
    Start a temperature automation
    """
    controller = run(  # noqa: F841
        automation=automation,
        target_temperature=target_temperature,
        target_growth_rate=target_growth_rate,
        skip_first_run=skip_first_run,
        duration=duration,
    )
