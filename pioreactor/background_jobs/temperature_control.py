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
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.utils import clamp


class TemperatureController(BackgroundJob):
    """

    This job publishes to

       pioreactor/<unit>/<experiment>/temperature_control/temperature

    the following:

        {
            "temperature": <float>,
            "timestamp": <ISO 8601 timestamp>
        }

    If you have your own thermo-couple, you can publish to this topic, with the same schema
    and all should just work™️. You'll need to provide your own feedback loops however.

    """

    automations = {}
    temperature = None

    editable_settings = ["temperature_automation", "temperature"]

    def __init__(self, temperature_automation, unit=None, experiment=None, **kwargs):
        super(TemperatureController, self).__init__(
            job_name="temperature_control", unit=unit, experiment=experiment
        )

        try:
            from TMP1075 import TMP1075
        except (NotImplementedError, ModuleNotFoundError):
            self.logger.info("TMP1075 not available; using MockTMP1075")
            from pioreactor.utils.mock import MockTMP1075 as TMP1075

        try:
            self.tmp_driver = TMP1075()
        except ValueError as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )
            raise IOError(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )

        self.pwm = self.setup_pwm()
        self.update_heater(0)

        self.read_external_temperature_timer = RepeatedTimer(
            60, self.read_external_temperature, run_immediately=True
        )
        self.read_external_temperature_timer.start()

        self.publish_temperature_timer = RepeatedTimer(
            10 * 60, self.evaluate_and_publish_temperature, run_immediately=True
        )
        self.publish_temperature_timer.start()

        self.temperature_automation = temperature_automation

        self.temperature_automation_job = self.automations[self.temperature_automation](
            unit=self.unit, experiment=self.experiment, parent=self, **kwargs
        )

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

        # TODO: new_duty_cycle should be capped at some value (since 100 will certainly push us over the temp maximum).

        if not self.pwm.is_locked():
            self._update_heater(new_duty_cycle)
            return True
        else:
            return False

    def update_heater_with_delta(self, delta_duty_cycle):
        """
        Update heater's duty cycle by `delta_duty_cycle` amount. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.update_heater(self.heater_duty_cycle + delta_duty_cycle)

    def read_external_temperature(self):
        """
        Read the current temperature from our sensor, in Celsius
        """
        try:
            pcb_temp = self.tmp_driver.get_temperature()
        except OSError:
            # could not find temp driver on i2c
            self.logger.error(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )
            raise IOError(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )

        self._check_if_exceeds_max_temp(pcb_temp)
        return pcb_temp

    ##### internal and private methods ########

    def set_temperature_automation(self, new_temperature_automation_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.temperature_automation_job.set_state("init")
        # self.temperature_automation_job.set_state("ready")
        # OR should just bail...
        algo_init = json.loads(new_temperature_automation_json)
        new_automation = algo_init.pop("temperature_automation")

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
            self.temperature_automation = new_automation

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        # TODO: this could move to the base class
        for attr in self.editable_settings:
            if attr in ["state"]:
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
        MAX_TEMP_TO_REDUCE_HEATING = 54.0
        MAX_TEMP_TO_DISABLE_HEATING = 56.0
        MAX_TEMP_TO_SHUTDOWN = 58.0

        if temp > MAX_TEMP_TO_REDUCE_HEATING:
            self.logger.debug(
                f"Temperature of heating surface has exceeded {MAX_TEMP_TO_REDUCE_HEATING}℃. This is close to our maximum recommended value. The heating PWM channel will be reduced to 90% its current value. Take caution when touching the heating surface and wetware."
            )

            self.update_heater(self.heater_duty_cycle * 0.90)

        elif temp > MAX_TEMP_TO_DISABLE_HEATING:
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
            pass

        try:
            self._update_heater(0)
            self.pwm.stop()
            self.pwm.cleanup()
        except AttributeError:
            pass

        self.clear_mqtt_cache()

    def setup_pwm(self):
        hertz = 5
        pin = PWM_TO_PIN[config.getint("PWM_reverse", "heating")]
        pwm = PWM(pin, hertz)
        pwm.start(0)
        return pwm

    def evaluate_and_publish_temperature(self):
        """
        1. lock PWM and turn off heater
        2. start recording temperatures from the sensor
        3. After collected M samples, pass to a model to approx temp
        4. assign temp to publish to .../temperature
        5. return heater to previous DC value and unlock heater
        """
        with self.pwm.lock_temporarily():

            previous_heater_dc = self.heater_duty_cycle
            self._update_heater(0)

            N_sample_points = 20
            time_between_samples = 10
            timestamp = current_utc_time()

            feature_vector = {}
            # feature_vector['prev_temp'] = self.temperature['temperature'] if self.temperature else 25

            for i in range(N_sample_points):
                feature_vector[
                    f"{time_between_samples * i}s"
                ] = self.read_external_temperature()
                time.sleep(time_between_samples)

            self.logger.debug(feature_vector)

            # update heater first, before setting the temperature. Why? A downstream process
            # might listen for the updating temperature, and update the heater (pid_stable),
            # and if we update here too late, we may overwrite their changes.
            # We also want to remove the lock first, so close this context early.
            self._update_heater(previous_heater_dc)

        try:
            approximated_temperature = self.approximate_temperature(feature_vector)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)

        self.temperature = {
            "temperature": approximated_temperature,
            "timestamp": timestamp,
        }

    def approximate_temperature(self, feature_vector):
        # check if we are using silent, if so, we can short this and return single value?s

        # some heuristic for now:
        import numpy as np

        prev_temp = 1_000_000
        for i, temp in enumerate(feature_vector.values()):
            if i > 0:
                delta_threshold = 0.1 + 0.2 / (1 + np.exp(-0.15 * (temp - 35)))
                if abs(prev_temp - temp) < delta_threshold:
                    return (temp + prev_temp) / 2

            prev_temp = temp

        return temp


def run(automation, **kwargs):
    try:
        TemperatureController(
            automation,
            unit=get_unit_name(),
            experiment=get_latest_experiment_name(),
            **kwargs,
        )

        signal.pause()
    except Exception as e:
        logger = create_logger("temperature_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


@click.command(
    name="temperature_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation",
    default="silent",
    help="set the automation of the system",
    show_default=True,
)
@click.pass_context
def click_temperature_control(ctx, automation):
    """
    Start a temperature automation.
    """
    run(  # noqa: F841
        automation=automation,
        **{ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )
