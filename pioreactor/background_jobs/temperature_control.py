# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor's temperature and take action. This is the core of the temperature automation.


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
message: a json object with required keyword arguments, see structs.TemperatureAutomation

"""
from __future__ import annotations

from contextlib import suppress
from time import sleep
from typing import Any
from typing import Optional

import click

from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.structs import Temperature
from pioreactor.structs import TemperatureAutomation
from pioreactor.utils import clamp
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime


class TemperatureController(BackgroundJob):
    """

    This job publishes to

        pioreactor/<unit>/<experiment>/temperature_control/temperature

    the following:

        {
            "temperature": <float>,
            "timestamp": <ISO 8601 timestamp>
        }

    Parameters
    ------------

    """

    MAX_TEMP_TO_REDUCE_HEATING = (
        63.0  # ~PLA glass transition temp, and I've gone safely above this an it's not a problem.
    )
    MAX_TEMP_TO_DISABLE_HEATING = 65.0  # probably okay, but can't stay here for too long
    MAX_TEMP_TO_SHUTDOWN = 66.0

    INFERENCE_SAMPLES_EVERY_T_SECONDS: float = 5.0
    INFERENCE_N_SAMPLES: int = 29
    INFERENCE_EVERY_N_SECONDS: float = 225.0
    inference_total_time: float = INFERENCE_SAMPLES_EVERY_T_SECONDS * INFERENCE_N_SAMPLES
    # PWM is on for (INFERENCE_EVERY_N_SECONDS - inference_total_time) seconds
    # the ratio of time a PWM is on is equal to (INFERENCE_EVERY_N_SECONDS - inference_total_time) / INFERENCE_EVERY_N_SECONDS

    job_name = "temperature_control"

    available_automations = {}  # type: ignore

    published_settings = {
        "automation": {"datatype": "Automation", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
        "temperature": {"datatype": "Temperature", "settable": False, "unit": "℃"},
        "heater_duty_cycle": {"datatype": "float", "settable": False, "unit": "%"},
    }

    def __init__(
        self,
        unit: str,
        experiment: str,
        automation_name: str,
        **kwargs,
    ) -> None:
        super().__init__(unit=unit, experiment=experiment)

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.clean_up()
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        if not hardware.is_heating_pcb_present():
            self.logger.error("Heating PCB must be attached to Pioreactor HAT")
            self.clean_up()
            raise exc.HardwareNotFoundError("Heating PCB must be attached to Pioreactor HAT")

        if whoami.is_testing_env():
            from pioreactor.utils.mock import MockTMP1075 as TMP1075
        else:
            from TMP1075 import TMP1075  # type: ignore

        self.heater_duty_cycle = 0.0
        self.pwm = self.setup_pwm()

        self.heating_pcb_tmp_driver = TMP1075(address=hardware.TEMP)
        self.read_external_temperature_timer = RepeatedTimer(
            53,
            self.read_external_temperature,
            run_immediately=False,
        ).start()

        self.publish_temperature_timer = RepeatedTimer(
            int(self.INFERENCE_EVERY_N_SECONDS),
            self.infer_temperature,
            run_after=self.INFERENCE_EVERY_N_SECONDS
            - self.inference_total_time,  # This gives an automation a "full" PWM cycle to be on before an inference starts.
            run_immediately=True,
        ).start()

        try:
            automation_class = self.available_automations[automation_name]
        except KeyError:
            self.logger.error(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )
            self.clean_up()
            raise KeyError(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )

        self.automation = TemperatureAutomation(automation_name=automation_name, args=kwargs)
        self.logger.info(f"Starting {self.automation}.")
        try:
            self.automation_job = automation_class(
                unit=self.unit,
                experiment=self.experiment,
                temperature_control_parent=self,
                **kwargs,
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.clean_up()
            raise e
        self.automation_name = self.automation.automation_name

        if whoami.is_testing_env() or self.seconds_since_last_active_heating() >= 10:
            # if we turn off heating and turn on again, without some sort of time to cool, the first temperature looks wonky
            self.temperature = Temperature(
                temperature=self.read_external_temperature(),
                timestamp=current_utc_datetime(),
            )

    @staticmethod
    def seconds_since_last_active_heating() -> float:
        with local_intermittent_storage("temperature_and_heating") as cache:
            if "last_heating_timestamp" in cache:
                return (
                    current_utc_datetime() - to_datetime(cache["last_heating_timestamp"])
                ).total_seconds()
            else:
                return 1_000_000

    def turn_off_heater(self) -> None:
        self._update_heater(0)
        self.pwm.cleanup()
        # we re-instantiate it as some other process may have messed with the channel.
        self.pwm = self.setup_pwm()
        self._update_heater(0)
        self.pwm.cleanup()

    def update_heater(self, new_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """

        if not self.pwm.is_locked():
            return self._update_heater(clamp(0.0, new_duty_cycle, 100.0))
        else:
            return False

    def update_heater_with_delta(self, delta_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle by `delta_duty_cycle` amount. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.update_heater(self.heater_duty_cycle + delta_duty_cycle)

    def read_external_temperature(self) -> float:
        return self._check_if_exceeds_max_temp(self._read_external_temperature())

    def _read_external_temperature(self) -> float:
        """
        Read the current temperature from our sensor, in Celsius
        """
        running_sum, running_count = 0.0, 0
        try:
            # check temp is fast, let's do it a few times to reduce variance.
            for i in range(5):
                running_sum += self.heating_pcb_tmp_driver.get_temperature()
                running_count += 1
                sleep(0.05)

        except OSError as e:
            self.logger.debug(e, exc_info=True)
            raise exc.HardwareNotFoundError(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find temperature sensor."
            )

        averaged_temp = running_sum / running_count
        if averaged_temp == 0.0 and self.automation_name != "only_record_temperature":
            # this is a hardware fluke, not sure why, see #308. We will return something very high to make it shutdown
            # todo: still needed? last observed on  July 18, 2022
            self.logger.error("Temp sensor failure. Switching off. See issue #308")
            self._update_heater(0.0)
            self.set_automation(TemperatureAutomation(automation_name="only_record_temperature"))

        with local_intermittent_storage("temperature_and_heating") as cache:
            cache["heating_pcb_temperature"] = averaged_temp
            cache["heating_pcb_temperature_at"] = current_utc_timestamp()

        return averaged_temp

    ##### internal and private methods ########

    def set_automation(self, algo_metadata: TemperatureAutomation) -> None:
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.automation_job.set_state("init")
        # self.automation_job.set_state("ready")
        # OR should just bail...

        assert isinstance(algo_metadata, TemperatureAutomation)

        # users sometimes take the "wrong path" and create a _new_ Thermostat with target_temperature=X
        # instead of just changing the target_temperature in their current Thermostat. We check for this condition,
        # and do the "right" thing for them.
        if (algo_metadata.automation_name == "thermostat") and (
            self.automation.automation_name == "thermostat"
        ):
            # just update the setting, and return
            self.logger.debug(
                "Bypassing changing automations, and just updating the setting on the existing Thermostat automation."
            )
            self.automation_job.set_target_temperature(
                float(algo_metadata.args["target_temperature"])
            )
            self.automation = algo_metadata
            return

        try:
            self.automation_job.clean_up()
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            sleep(1)
            self.set_automation(algo_metadata)

        # reset heater back to 0.
        self._update_heater(0)

        try:
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = self.available_automations[algo_metadata.automation_name](
                unit=self.unit,
                experiment=self.experiment,
                temperature_control_parent=self,
                **algo_metadata.args,
            )
            self.automation = algo_metadata
            self.automation_name = algo_metadata.automation_name

            # since we are changing automations inside a controller, we know that the latest temperature reading is recent, so we can
            # pass it on to the new automation.
            # this is most useful when temp-control is initialized with only_record_temperature, and then quickly switched over to thermostat.
            self.automation_job._set_latest_temperature(self.temperature)

        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations.",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations."
            )
        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def _update_heater(self, new_duty_cycle: float) -> bool:
        self.heater_duty_cycle = clamp(0.0, round(float(new_duty_cycle), 2), 100.0)
        self.pwm.change_duty_cycle(self.heater_duty_cycle)

        if self.heater_duty_cycle == 0.0:
            with local_intermittent_storage("temperature_and_heating") as cache:
                cache["last_heating_timestamp"] = current_utc_timestamp()

        return True

    def _check_if_exceeds_max_temp(self, temp: float) -> float:
        if temp > self.MAX_TEMP_TO_SHUTDOWN:
            self.logger.error(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_SHUTDOWN}℃ - currently {temp}℃. This is beyond our recommendations. Shutting down Raspberry Pi to prevent further problems. Take caution when touching the heating surface and wetware."
            )
            self._update_heater(0)

            self.blink_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

            from subprocess import call

            call("sudo shutdown now --poweroff", shell=True)

        elif temp > self.MAX_TEMP_TO_DISABLE_HEATING:
            self.blink_error_code(error_codes.PCB_TEMPERATURE_TOO_HIGH)

            self.logger.warning(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_DISABLE_HEATING}℃ - currently {temp}℃. This is beyond our recommendations. The heating PWM channel will be forced to 0 and the automation turned to only_record_temperature. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(0)

            if self.automation_name != "only_record_temperature":
                self.set_automation(
                    TemperatureAutomation(automation_name="only_record_temperature")
                )

        elif temp > self.MAX_TEMP_TO_REDUCE_HEATING:
            self.logger.debug(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_REDUCE_HEATING}℃ - currently {temp}℃. This is close to our maximum recommended value. The heating PWM channel will be reduced to 90% its current value. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(self.heater_duty_cycle * 0.9)

        return temp

    def on_sleeping(self) -> None:
        self.automation_job.set_state(self.SLEEPING)

    def on_sleeping_to_ready(self) -> None:
        self.automation_job.set_state(self.READY)

    def on_disconnected(self) -> None:
        with suppress(AttributeError):
            self.read_external_temperature_timer.cancel()
            self.publish_temperature_timer.cancel()

        with suppress(AttributeError):
            self._update_heater(0)
            self.pwm.cleanup()

        with suppress(AttributeError):
            self.automation_job.clean_up()

    def setup_pwm(self) -> PWM:
        hertz = 8  # technically this doesn't need to be high: it could even be 1hz. However, we want to smooth it's
        # impact (mainly: current sink), over the second. Ex: imagine freq=1hz, dc=40%, and the pump needs to run for
        # 0.3s. The influence of when the heat is one on the pump can be significant in a power-constrained system.
        pin = hardware.PWM_TO_PIN[hardware.HEATER_PWM_TO_PIN]
        pwm = PWM(pin, hertz, unit=self.unit, experiment=self.experiment)
        pwm.start(0)
        return pwm

    @staticmethod
    def _get_room_temperature():
        # TODO: improve somehow
        return 22.0

    def infer_temperature(self) -> None:
        """
        1. lock PWM and turn off heater
        2. start recording temperatures from the sensor
        3. After collected M samples, pass to a model to approx temp
        4. assign temp to publish to ../temperature
        5. return heater to previous DC value and unlock heater
        """

        # this will pause heating for (N_sample_points * time_between_samples) seconds
        N_sample_points = self.INFERENCE_N_SAMPLES
        time_between_samples = self.INFERENCE_SAMPLES_EVERY_T_SECONDS

        assert not self.pwm.is_locked(), "PWM is locked - it shouldn't be though!"
        with self.pwm.lock_temporarily():
            previous_heater_dc = self.heater_duty_cycle

            features: dict[str, Any] = {}
            features["previous_heater_dc"] = previous_heater_dc

            # figure out a better way to estimate this... luckily inference is not too sensitive to this parameter.
            # users can override this function with something more accurate later.
            features["room_temp"] = self._get_room_temperature()

            # turn off active heating, and start recording decay
            self._update_heater(0)
            time_series_of_temp = []

            try:
                for i in range(N_sample_points):
                    time_series_of_temp.append(self.read_external_temperature())
                    sleep(time_between_samples)

                    if self.state != self.READY:
                        # if our state changes in this loop, exit. Note that the finally block is still called.
                        return

            except exc.HardwareNotFoundError as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                raise e
            finally:
                # we turned off the heater above - we should always turn if back on if there is an error.

                # update heater first before publishing the temperature. Why? A downstream process
                # might listen for the updating temperature, and update the heater (pid_thermostat),
                # and if we update here too late, we may overwrite their changes.
                # We also want to remove the lock first, so close this context early.
                self._update_heater(previous_heater_dc)

        features["time_series_of_temp"] = time_series_of_temp
        self.logger.debug(f"{features=}")

        try:
            self.temperature = Temperature(
                temperature=round(self.approximate_temperature(features), 2),
                timestamp=current_utc_datetime(),
            )

        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)

    def approximate_temperature(self, features: dict[str, Any]) -> float:
        """
        models

            temp = b * exp(p * t) + c * exp(q * t) + room_temp

        Reference
        -------------
        https://www.scribd.com/doc/14674814/Regressions-et-equations-integrales
        page 71 - 72


        Extensions
        --------------

        1. It's possible that we can determine if the vial is in the sleeve by examining the heat loss coefficient.
        2. We have prior information about what p, q are => we have prior information about A, B. We use this.
           From the equations, B = p + q, A = -p * q, so weak prior in B ~ Normal(-0.143, ...), A = Normal(-0.00042, ....)
        3. Room temp has a moderate impact on inference: ~0.30C over a wide range of values
        """

        if features["previous_heater_dc"] == 0:
            return features["time_series_of_temp"][-1]

        import numpy as np
        from numpy import exp

        times_series = features["time_series_of_temp"]
        room_temp = features["room_temp"]
        n = len(times_series)
        y = np.array(times_series) - room_temp
        x = np.arange(n)  # scaled by factor of 1/10 seconds

        # first regression
        S = np.zeros(n)
        SS = np.zeros(n)
        for i in range(1, n):
            S[i] = S[i - 1] + 0.5 * (y[i - 1] + y[i]) * (x[i] - x[i - 1])
            SS[i] = SS[i - 1] + 0.5 * (S[i - 1] + S[i]) * (x[i] - x[i - 1])

        # priors chosen based on historical data, penalty values pretty arbitrary, note: B = p + q, A = -p * q
        A_penalizer, A_prior = 100.0, -0.0012
        B_penalizer, B_prior = 50.0, -0.325

        M1 = np.array(
            [
                [
                    (SS**2).sum() + A_penalizer,
                    (SS * S).sum(),
                    (SS * x).sum(),
                    (SS).sum(),
                ],
                [(SS * S).sum(), (S**2).sum() + B_penalizer, (S * x).sum(), (S).sum()],
                [(SS * x).sum(), (S * x).sum(), (x**2).sum(), (x).sum()],
                [(SS).sum(), (S).sum(), (x).sum(), n],
            ]
        )
        Y1 = np.array(
            [
                (y * SS).sum() + A_penalizer * A_prior,
                (y * S).sum() + B_penalizer * B_prior,
                (y * x).sum(),
                y.sum(),
            ]
        )

        try:
            A, B, _, _ = np.linalg.solve(M1, Y1)
        except np.linalg.LinAlgError:
            self.logger.error("Error in temperature inference.")
            self.logger.debug("Error in temperature inference", exc_info=True)
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            raise ValueError()

        if (B**2 + 4 * A) < 0:
            # something when wrong in the data collection - the data doesn't look enough like a sum of two expos
            self.logger.error("Error in temperature inference.")
            self.logger.debug(f"Error in temperature inference: {(B ** 2 + 4 * A)=} < 0")
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            raise ValueError()

        p = 0.5 * (
            B + np.sqrt(B**2 + 4 * A)
        )  # usually p ~= -0.0000 to -0.0100, but is a function of the temperature (Recall it describes the heat loss to ambient)
        q = 0.5 * (
            B - np.sqrt(B**2 + 4 * A)
        )  # usually q ~= -0.130 to -0.160, but is a not really a function of the temperature. Oddly enough, it looks periodic with freq ~1hr...

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
            self.logger.error("Error in temperature inference.")
            self.logger.debug("Error in temperature inference's second regression.", exc_info=True)
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            raise ValueError()

        alpha, beta = b, p

        # this weighting is from evaluating the "average" temp over the period: 1/n int_0^n R + a*exp(b*s) ds
        # cast from numpy float to python float
        return float(room_temp + alpha * exp(beta * n))
        # return float(room_temp + alpha * (exp(beta * n) - 1)/(beta * n))


def start_temperature_control(
    automation_name: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> TemperatureController:
    return TemperatureController(
        unit=unit or whoami.get_unit_name(),
        experiment=experiment or whoami.get_latest_experiment_name(),
        automation_name=automation_name,
        **kwargs,
    )


@click.command(
    name="temperature_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    help="set the automation of the system",
    show_default=True,
    required=True,
)
@click.pass_context
def click_temperature_control(ctx, automation_name: str) -> None:
    """
    Start a temperature automation.
    """
    import os

    os.nice(1)

    kwargs = {
        ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)
    }
    if "skip_first_run" in kwargs:
        del kwargs["skip_first_run"]

    tc = start_temperature_control(
        automation_name=automation_name,
        **kwargs,
    )
    tc.block_until_disconnected()
