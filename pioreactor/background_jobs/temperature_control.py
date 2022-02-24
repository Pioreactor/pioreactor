# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the temperature automation.


The temperature is determined using a temperature sensor outside the vial, on the base PCB. This means there is some
difference between the recorded PCB temperature, and the liquid temperature.

The same PCB is used for heating the vial - so how do we remove the effect of PCB heating from temperature. The general
algorithm is below, housed in TemperatureController

    1. Turn on heating, the amount controlled by the TemperatureController.heater_duty_cycle.
    2. Every N minutes, we trigger a sequence:
        1. Turn off heating completely (a lock is introduced so other jobs can't change this)
        2. Every M seconds, record the temperature on the PCB.
        3. Use the series of PCB temperatures to infer the temperature of vial.


To change the automation over MQTT,

topic: `pioreactor/<unit>/<experiment>/temperture_control/automation/set`
message: a json object with required keyword arguments. Specify the new automation with key `"automation_name"`.

"""
from __future__ import annotations

from time import sleep
from typing import Any
from typing import Optional

import click

from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.structs import Automation
from pioreactor.structs import Temperature
from pioreactor.utils import clamp
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_time
from pioreactor.utils.timing import RepeatedTimer


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


    Parameters
    ------------
    eval_and_publish_immediately: bool, default True
        evaluate and publish the temperature once the class is created (in the background)
        TODO: do I need this still?
    """

    MAX_TEMP_TO_REDUCE_HEATING = 58.0
    MAX_TEMP_TO_DISABLE_HEATING = 62.0  # ~PLA glass transition temp
    MAX_TEMP_TO_SHUTDOWN = 64.0

    automations = {}  # type: ignore

    published_settings = {
        "automation": {"datatype": "Automation", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
        "temperature": {"datatype": "Temperature", "settable": False, "unit": "℃"},
        "heater_duty_cycle": {"datatype": "float", "settable": False, "unit": "%"},
    }
    temperature: Optional[Temperature] = None

    def __init__(
        self,
        automation_name: str,
        unit: str,
        experiment: str,
        eval_and_publish_immediately: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(job_name="temperature_control", unit=unit, experiment=experiment)

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.set_state(self.DISCONNECTED)
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        if not hardware.is_heating_pcb_present():
            self.logger.error("Heating PCB must be attached to Pioreactor HAT")
            self.set_state(self.DISCONNECTED)
            raise exc.HardwareNotFoundError(
                "Heating PCB must be attached to Pioreactor HAT"
            )

        if whoami.is_testing_env():
            self.logger.debug("TMP1075 not available; using MockTMP1075")
            from pioreactor.utils.mock import MockTMP1075 as TMP1075
        else:
            from TMP1075 import TMP1075  # type: ignore

        self.pwm = self.setup_pwm()
        self.update_heater(0)

        self.tmp_driver = TMP1075()
        self.read_external_temperature_timer = RepeatedTimer(
            37,
            self.read_external_temperature_and_check_temp,
            run_immediately=False,
        ).start()

        self.publish_temperature_timer = RepeatedTimer(
            4 * 60,
            self.evaluate_and_publish_temperature,
            run_immediately=eval_and_publish_immediately,
            run_after=60,
        ).start()

        try:
            automation_class = self.automations[automation_name]
        except KeyError:
            raise KeyError(
                f"Unable to find automation {automation_name}. Available automations are {list(self.automations.keys())}"
            )

        self.automation = Automation(
            automation_name=automation_name, automation_type="temperature", args=kwargs
        )
        self.logger.info(f"Starting {self.automation}.")
        try:
            self.automation_job = automation_class(
                unit=self.unit, experiment=self.experiment, parent=self, **kwargs
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.set_state(self.DISCONNECTED)
            raise e
        self.automation_name = self.automation.automation_name

        self.temperature = Temperature(
            temperature=self.read_external_temperature(),
            timestamp=current_utc_time(),
        )

    def turn_off_heater(self) -> None:
        self._update_heater(0)
        self.pwm.stop()
        self.pwm.cleanup()
        # we re-instantiate it as some other process may have messed with the channel.
        self.pwm = self.setup_pwm()
        self._update_heater(0)
        self.pwm.stop()

    def update_heater(self, new_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """

        if not self.pwm.is_locked():
            self._update_heater(clamp(0.0, new_duty_cycle, 90.0))
            return True
        else:
            return False

    def update_heater_with_delta(self, delta_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle by `delta_duty_cycle` amount. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.update_heater(
            clamp(0, self.heater_duty_cycle + delta_duty_cycle, 100)
        )

    def read_external_temperature_and_check_temp(self) -> float:
        pcb_temp = self.read_external_temperature()
        self._check_if_exceeds_max_temp(pcb_temp)
        return pcb_temp

    def read_external_temperature(self) -> float:
        """
        Read the current temperature from our sensor, in Celsius
        """
        try:
            # check temp is fast, let's do it twice to reduce variance.
            return 0.5 * (
                self.tmp_driver.get_temperature() + self.tmp_driver.get_temperature()
            )
        except OSError:
            # could not find temp driver on i2c
            self.logger.error(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )
            raise exc.HardwareNotFoundError(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find I²C for temperature driver."
            )

    ##### internal and private methods ########

    def set_automation(self, algo_metadata: Automation) -> None:
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.automation_job.set_state("init")
        # self.automation_job.set_state("ready")
        # OR should just bail...

        if algo_metadata.automation_type != "temperature":
            raise ValueError("algo_metadata.automation_type != 'temperature'")

        try:
            self.automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            sleep(1)
            self.set_automation(algo_metadata)

        # reset heater back to 0.
        self._update_heater(0)

        try:
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = self.automations[algo_metadata.automation_name](
                unit=self.unit,
                experiment=self.experiment,
                parent=self,
                **algo_metadata.args,
            )
            self.automation = algo_metadata
            self.automation_name = algo_metadata.automation_name

        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.automations.keys())}",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.automations.keys())}"
            )
        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def _update_heater(self, new_duty_cycle: float) -> None:
        self.heater_duty_cycle = round(float(new_duty_cycle), 5)
        self.pwm.change_duty_cycle(self.heater_duty_cycle)

    def _check_if_exceeds_max_temp(self, temp: float) -> None:

        if temp > self.MAX_TEMP_TO_SHUTDOWN:
            self.logger.error(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_SHUTDOWN}℃ - currently {temp} ℃. This is beyond our recommendations. Shutting down Raspberry Pi to prevent further problems. Take caution when touching the heating surface and wetware."
            )

            from subprocess import call

            call("sudo shutdown --poweroff", shell=True)

        elif temp > self.MAX_TEMP_TO_DISABLE_HEATING:

            self.blink_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

            self.logger.warning(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_DISABLE_HEATING}℃ - currently {temp} ℃. This is beyond our recommendations. The heating PWM channel will be forced to 0 and the automation turned to Silent. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(0)

            if self.automation_name != "silent":
                self.set_automation(
                    Automation(automation_name="silent", automation_type="temperature")
                )

        elif temp > self.MAX_TEMP_TO_REDUCE_HEATING:

            self.blink_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

            self.logger.debug(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_REDUCE_HEATING}℃ - currently {temp} ℃. This is close to our maximum recommended value. The heating PWM channel will be reduced to 90% its current value. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(self.heater_duty_cycle * 0.9)

    def on_sleeping(self) -> None:
        self.automation_job.set_state(self.SLEEPING)

    def on_sleeping_to_ready(self) -> None:
        self.automation_job.set_state(self.READY)

    def on_disconnected(self) -> None:
        try:
            self.automation_job.set_state(self.DISCONNECTED)
        except AttributeError:
            # if disconnect is called right after starting, temperature_automation_job isn't instantiated
            pass

        try:
            self.read_external_temperature_timer.cancel()
            self.publish_temperature_timer.cancel()
        except AttributeError:
            pass

        try:
            self._update_heater(0)
            self.pwm.stop()
            self.pwm.cleanup()
        except AttributeError:
            pass

    def setup_pwm(self) -> PWM:
        hertz = 1
        pin = hardware.PWM_TO_PIN[hardware.HEATER_PWM_TO_PIN]
        pin = hardware.PWM_TO_PIN[
            config.get("PWM_reverse", "heating")
        ]  # TODO: remove this.
        pwm = PWM(pin, hertz, unit=self.unit, experiment=self.experiment)
        pwm.start(0)
        return pwm

    def evaluate_and_publish_temperature(self) -> None:
        """
        1. lock PWM and turn off heater
        2. start recording temperatures from the sensor
        3. After collected M samples, pass to a model to approx temp
        4. assign temp to publish to ../temperature
        5. return heater to previous DC value and unlock heater
        """
        assert not self.pwm.is_locked(), "PWM is locked - it shouldn't be though!"
        with self.pwm.lock_temporarily():

            previous_heater_dc = self.heater_duty_cycle
            self._update_heater(0)

            # we pause heating for (N_sample_points * time_between_samples) seconds
            N_sample_points = 30
            time_between_samples = 5

            features: dict[str, Any] = {}
            features["prev_temp"] = (
                self.temperature.temperature if (self.temperature is not None) else None
            )
            features["previous_heater_dc"] = previous_heater_dc

            time_series_of_temp = []
            for i in range(N_sample_points):
                time_series_of_temp.append(self.read_external_temperature())
                sleep(time_between_samples)

                if self.state != self.READY:
                    # if our state changes in this loop, exit.
                    return

            features["time_series_of_temp"] = time_series_of_temp

            self.logger.debug(features)

            # update heater first, before publishing the temperature. Why? A downstream process
            # might listen for the updating temperature, and update the heater (pid_stable),
            # and if we update here too late, we may overwrite their changes.
            # We also want to remove the lock first, so close this context early.
            self._update_heater(previous_heater_dc)

        try:
            approximated_temperature = self.approximate_temperature(features)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)

        self.temperature = Temperature(
            temperature=approximated_temperature,
            timestamp=current_utc_time(),
        )

    def approximate_temperature(self, features: dict[str, Any]) -> float:
        """
        models

            temp = b * exp(p * t) + c * exp(q * t) + ROOM_TEMP

        Reference
        -------------
        https://www.scribd.com/doc/14674814/Regressions-et-equations-integrales
        page 71 - 72


        It's possible that we can determine if the vial is in using the heat loss coefficient. Quick look:
        when the vial is in, heat coefficient is ~ -0.008, when not in, coefficient is ~ -0.028.

        """

        if features["previous_heater_dc"] == 0:
            return features["time_series_of_temp"][-1]

        import numpy as np
        from numpy import exp

        ROOM_TEMP = 10.0  # ??

        times_series = features["time_series_of_temp"]

        n = len(times_series)
        y = np.array(times_series) - ROOM_TEMP
        x = np.arange(n)  # scaled by factor of 1/10 seconds

        S = np.zeros(n)
        SS = np.zeros(n)
        for i in range(1, n):
            S[i] = S[i - 1] + 0.5 * (y[i - 1] + y[i]) * (x[i] - x[i - 1])
            SS[i] = SS[i - 1] + 0.5 * (S[i - 1] + S[i]) * (x[i] - x[i - 1])

        # first regression
        M1 = np.array(
            [
                [(SS**2).sum(), (SS * S).sum(), (SS * x).sum(), (SS).sum()],
                [(SS * S).sum(), (S**2).sum(), (S * x).sum(), (S).sum()],
                [(SS * x).sum(), (S * x).sum(), (x**2).sum(), (x).sum()],
                [(SS).sum(), (S).sum(), (x).sum(), n],
            ]
        )
        Y1 = np.array([(y * SS).sum(), (y * S).sum(), (y * x).sum(), y.sum()])

        try:
            A, B, _, _ = np.linalg.solve(M1, Y1)
        except np.linalg.LinAlgError:
            self.logger.error("Error in first regression.")
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            return features["prev_temp"]

        if (B**2 + 4 * A) < 0:
            # something when wrong in the data collection - the data doesn't look enough like a sum of two expos
            self.logger.error(f"Error in regression: {(B ** 2 + 4 * A)=} < 0")
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            return features["prev_temp"]

        p = 0.5 * (B + np.sqrt(B**2 + 4 * A))
        q = 0.5 * (B - np.sqrt(B**2 + 4 * A))

        # second regression
        M2 = np.array(
            [
                [exp(2 * p * x).sum(), exp((p + q) * x).sum()],
                [exp((q + p) * x).sum(), exp(2 * q * x).sum()],
            ]
        )
        Y2 = np.array([(y * exp(p * x)).sum(), (y * exp(q * x)).sum()])

        try:
            b, c = np.linalg.solve(M2, Y2)
        except np.linalg.LinAlgError:
            self.logger.error("Error in second regression")
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            return features["prev_temp"]

        if abs(p) < abs(q):
            # since the regression can have identifiable problems, we use
            # our domain knowledge to choose the pair that has the lower heat transfer coefficient.
            alpha, beta = b, p
        else:
            alpha, beta = c, q

        self.logger.debug(f"{b=}, {c=}, {p=} , {q=}")

        temp_at_start_of_obs = ROOM_TEMP + alpha * exp(beta * 0)
        temp_at_end_of_obs = ROOM_TEMP + alpha * exp(beta * n)

        # the recent estimate weighted because I trust the predicted temperature at the start of observation more
        # than the predicted temperature at the end.
        return float(2 / 3 * temp_at_start_of_obs + 1 / 3 * temp_at_end_of_obs)


def start_temperature_control(
    automation_name: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> TemperatureController:
    return TemperatureController(
        automation_name=automation_name,
        unit=unit or whoami.get_unit_name(),
        experiment=experiment or whoami.get_latest_experiment_name(),
        **kwargs,
    )


@click.command(
    name="temperature_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    default="silent",
    help="set the automation of the system",
    show_default=True,
)
@click.pass_context
def click_temperature_control(ctx, automation_name: str) -> None:
    """
    Start a temperature automation.
    """
    tc = start_temperature_control(
        automation_name=automation_name,
        **{
            ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1]
            for i in range(0, len(ctx.args), 2)
        },
    )
    tc.block_until_disconnected()
