# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import suppress
from threading import Event
from time import sleep
from typing import Any
from typing import Optional

import click

from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.automations.base import AutomationJob
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.structs import Temperature
from pioreactor.utils import clamp
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import whoami
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime
from pioreactor.version import rpi_version_info


class classproperty(property):
    def __get__(self, obj, objtype=None):
        return self.fget(objtype)


def is_20ml_v1() -> bool:
    return whoami.get_pioreactor_model() == "pioreactor_20ml" and whoami.get_pioreactor_version() == (1, 0)


class TemperatureAutomationJob(AutomationJob):
    """
    This is the super class that Temperature automations inherit from.
    The `execute` function, which is what subclasses will define, is updated every time a new temperature is computed.
    Temperatures are updated every `INFERENCE_EVERY_N_SECONDS` seconds.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/temperature_automation/<setting>/set` value

    """

    @classproperty
    def INFERENCE_SAMPLES_EVERY_T_SECONDS(cls) -> float:
        return 5.0

    @classproperty
    def MAX_TEMP_TO_REDUCE_HEATING(cls) -> float:
        return 63.0 if is_20ml_v1() else 78.0

    @classproperty
    def MAX_TEMP_TO_DISABLE_HEATING(cls) -> float:
        return 65.0 if is_20ml_v1() else 80.0

    @classproperty
    def MAX_TEMP_TO_SHUTDOWN(cls) -> float:
        return 66.0 if is_20ml_v1() else 85.0

    @classproperty
    def INFERENCE_N_SAMPLES(cls) -> int:
        return 29 if is_20ml_v1() else 21

    @classproperty
    def INFERENCE_EVERY_N_SECONDS(cls) -> float:
        return 225.0 if is_20ml_v1() else 200.0

    latest_temperature = None
    previous_temperature = None

    automation_name = "temperature_automation_base"  # is overwritten in subclasses
    job_name = "temperature_automation"

    published_settings: dict[str, pt.PublishableSetting] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of TemperatureAutomationJob
        if (
            hasattr(cls, "automation_name")
            and getattr(cls, "automation_name") != "temperature_automation_base"
        ):
            available_temperature_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        **kwargs,
    ) -> None:
        super(TemperatureAutomationJob, self).__init__(unit, experiment)

        self.add_to_published_settings(
            "temperature", {"datatype": "Temperature", "settable": False, "unit": "℃"}
        )

        self.add_to_published_settings(
            "heater_duty_cycle",
            {"datatype": "float", "settable": False, "unit": "%"},
        )

        if not hardware.is_heating_pcb_present():
            self.logger.error("Heating PCB must be attached to Pioreactor HAT")
            self.clean_up()
            raise exc.HardwareNotFoundError("Heating PCB must be attached to Pioreactor HAT")

        if whoami.is_testing_env():
            from pioreactor.utils.mock import MockTMP1075 as TMP1075
        else:
            from pioreactor.utils.temps import TMP1075  # type: ignore

        self.inference_total_time = self.INFERENCE_SAMPLES_EVERY_T_SECONDS * self.INFERENCE_N_SAMPLES
        assert self.INFERENCE_EVERY_N_SECONDS > self.inference_total_time
        # PWM is on for (INFERENCE_EVERY_N_SECONDS - inference_total_time) seconds
        # the ratio of time a PWM is on is equal to (INFERENCE_EVERY_N_SECONDS - inference_total_time) / INFERENCE_EVERY_N_SECONDS

        self.heater_duty_cycle = 0.0
        self.pwm = self.setup_pwm()
        self._exit_event = Event()

        self.heating_pcb_tmp_driver = TMP1075(address=hardware.TEMP)

        self.read_external_temperature_timer = RepeatedTimer(
            53,
            self.read_external_temperature,
            job_name=self.job_name,
            run_immediately=False,
            logger=self.logger,
        ).start()

        self.publish_temperature_timer = RepeatedTimer(
            int(self.INFERENCE_EVERY_N_SECONDS),
            self.infer_temperature,
            job_name=self.job_name,
            run_after=self.INFERENCE_EVERY_N_SECONDS
            - self.inference_total_time,  # This gives an automation a "full" PWM cycle to be on before an inference starts.
            run_immediately=True,
        ).start()

        self.latest_temperture_at = current_utc_datetime()

    def on_init_to_ready(self):
        if whoami.is_testing_env() or self.seconds_since_last_active_heating() >= 10:
            # if we turn off heating and turn on again, without some sort of time to cool, the first temperature looks wonky
            self.temperature = Temperature(
                temperature=self.read_external_temperature(),
                timestamp=current_utc_datetime(),
            )

            self._set_latest_temperature(self.temperature)

    @staticmethod
    def seconds_since_last_active_heating() -> float:
        with local_intermittent_storage("temperature_and_heating") as cache:
            if "last_heating_timestamp" in cache:
                return (current_utc_datetime() - to_datetime(cache["last_heating_timestamp"])).total_seconds()
            else:
                return 1_000_000

    def turn_off_heater(self) -> None:
        self._update_heater(0)
        self.pwm.clean_up()

        # we re-instantiate it as some other process may have messed with the channel.
        self.pwm = self.setup_pwm()
        self.pwm.change_duty_cycle(0)
        self.pwm.clean_up()

    def update_heater(self, new_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle. This function checks for the PWM lock, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """

        if not self.pwm.is_locked():
            return self._update_heater(new_duty_cycle)
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

    def is_heater_pwm_locked(self) -> bool:
        """
        Check if the heater PWM channels is locked
        """
        return self.pwm.is_locked()

    ########## Private & internal methods

    def _read_external_temperature(self) -> float:
        """
        Read the current temperature from our sensor, in Celsius
        """
        running_sum, running_count = 0.0, 0
        try:
            # check temp is fast, let's do it a few times to reduce variance.
            for i in range(6):
                running_sum += self.heating_pcb_tmp_driver.get_temperature()
                running_count += 1
                sleep(0.05)

        except OSError as e:
            self.logger.debug(e, exc_info=True)
            raise exc.HardwareNotFoundError(
                "Is the Heating PCB attached to the Pioreactor HAT? Unable to find temperature sensor."
            )

        averaged_temp = running_sum / running_count

        with local_intermittent_storage("temperature_and_heating") as cache:
            cache["heating_pcb_temperature"] = averaged_temp
            cache["heating_pcb_temperature_at"] = current_utc_timestamp()

        return averaged_temp

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
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_DISABLE_HEATING}℃ - currently {temp}℃. This is beyond our recommendations. The heating PWM channel will be forced to 0. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(0)

        elif temp > self.MAX_TEMP_TO_REDUCE_HEATING:
            self.logger.debug(
                f"Temperature of heating surface has exceeded {self.MAX_TEMP_TO_REDUCE_HEATING}℃ - currently {temp}℃. This is close to our maximum recommended value. The heating PWM channel will be reduced to 90% its current value. Take caution when touching the heating surface and wetware."
            )

            self._update_heater(self.heater_duty_cycle * 0.9)

        return temp

    def on_disconnected(self) -> None:
        self._exit_event.set()

        with suppress(AttributeError):
            self.publish_temperature_timer.cancel()
            self.read_external_temperature_timer.cancel()

        # this comes after, in case the automation changes dc after publishing the temp.
        with suppress(AttributeError):
            self.turn_off_heater()

    def on_sleeping(self) -> None:
        self.publish_temperature_timer.pause()
        self._update_heater(0)

    def on_sleeping_to_ready(self) -> None:
        self.publish_temperature_timer.unpause()

    def setup_pwm(self) -> PWM:
        hertz = 16  # technically this doesn't need to be high: it could even be 1hz. However, we want to smooth it's
        # impact (mainly: current sink), over the second. Ex: imagine freq=1hz, dc=40%, and the pump needs to run for
        # 0.3s. The influence of when the heat is one on the pump can be significant in a power-constrained system.
        pin = hardware.PWM_TO_PIN[hardware.HEATER_PWM_TO_PIN]
        pwm = PWM(
            pin,
            hertz,
            unit=self.unit,
            experiment=self.experiment,
            pub_client=self.pub_client,
            logger=self.logger,
        )
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

            # add how much heat/energy we just applied
            features["previous_heater_dc"] = previous_heater_dc

            # figure out a better way to estimate this... luckily inference is not too sensitive to this parameter.
            # users can override this function with something more accurate later.
            features["room_temp"] = self._get_room_temperature()

            # B models have a hotter ambient env. TODO: what about As?
            features["is_rpi_zero"] = rpi_version_info.startswith("Raspberry Pi Zero")

            # the amount of liquid in the vial is a factor!
            features["volume"] = 0.5 * (
                config.getfloat("bioreactor", "initial_volume_ml")
                + config.getfloat("bioreactor", "max_volume_ml")
            )

            # turn off active heating, and start recording decay
            self._update_heater(0)
            time_series_of_temp = []

            try:
                for i in range(N_sample_points):
                    time_series_of_temp.append(self.read_external_temperature())
                    sleep(time_between_samples)

                    if self._exit_event.is_set():
                        # if our state changes in this loop, exit. Note that the finally block is still called.
                        previous_heater_dc = 0
                        return

            except exc.HardwareNotFoundError as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                raise e
            finally:
                # update heater first before publishing the temperature. Why? A downstream process
                # might listen for the updating temperature, and update the heater (pid_thermostat),
                # and if we update here too late, we may overwrite their changes.
                # We also want to remove the lock first, so close this context early.
                self._update_heater(previous_heater_dc)

        features["time_series_of_temp"] = time_series_of_temp
        self.logger.debug(f"{features=}")

        try:
            if whoami.get_pioreactor_model() == "pioreactor_20ml":
                if whoami.get_pioreactor_version() == (1, 0):
                    inferred_temperature = self.approximate_temperature_20_1_0(features)
                elif whoami.get_pioreactor_version() >= (1, 1):
                    inferred_temperature = self.approximate_temperature_20_2_0(features)
            elif whoami.get_pioreactor_model() == "pioreactor_40ml":
                inferred_temperature = self.approximate_temperature_20_2_0(features)  # TODO: change me back
            else:
                raise ValueError("Unknown Pioreactor model.")

            self.temperature = Temperature(
                temperature=round(inferred_temperature, 2),
                timestamp=current_utc_datetime(),
            )
            self._set_latest_temperature(self.temperature)

        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)

    @staticmethod
    def approximate_temperature_40_1_0(features: dict[str, Any]) -> float:
        raise NotImplementedError("This model has not been implemented yet.")

    @staticmethod
    def approximate_temperature_20_1_0(features: dict[str, Any]) -> float:
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
            raise ValueError(f"Error in temperature inference. {x=}, {y=}")

        if (B**2 + 4 * A) < 0:
            # something when wrong in the data collection - the data doesn't look enough like a sum of two expos
            raise ValueError(f"Error in temperature inference. {x=}, {y=}")

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
            raise ValueError(f"Error in temperature inference. {x=}, {y=}")

        alpha, beta = b, p

        # this weighting is from evaluating the "average" temp over the period: 1/n int_0^n R + a*exp(b*s) ds
        # cast from numpy float to python float
        return float(room_temp + alpha * exp(beta * n))
        # return float(room_temp + alpha * (exp(beta * n) - 1)/(beta * n))

    @staticmethod
    def approximate_temperature_20_2_0(features: dict[str, Any]) -> float:
        """
        This uses linear regression from historical data
        """
        if features["previous_heater_dc"] == 0:
            return features["time_series_of_temp"][-1]

        X = [features["previous_heater_dc"]] + features["time_series_of_temp"]

        # normalize to ~1.0, as we do this in training.
        X = [x / 35.0 for x in X]

        # add in non-linear features
        X.append(X[1] ** 2)
        X.append(X[20] * X[0])

        coefs = [
            -1.37221255e01,
            1.50807347e02,
            1.52808570e01,
            -7.17124615e01,
            -8.15352596e01,
            -5.82053398e01,
            -8.49915201e01,
            -3.69729300e01,
            -8.51994806e-02,
            1.12635670e01,
            3.37434235e01,
            3.36348041e01,
            4.25731033e01,
            6.72551219e01,
            8.37883314e01,
            6.29508694e01,
            4.95735854e01,
            1.86594862e01,
            3.12848519e-01,
            -3.82815596e01,
            -5.62834504e01,
            -9.27840943e01,
            -7.62113224e00,
            8.18877406e00,
        ]

        intercept = -6.171633633597331

        def dot_product(vec1: list, vec2: list) -> float:
            if len(vec1) != len(vec2):
                raise ValueError(f"Vectors must be of the same length. Got {len(vec1)=}, {len(vec2)=}")
            return sum(x * y for x, y in zip(vec1, vec2))

        return dot_product(coefs, X) + intercept

    def _set_latest_temperature(self, temperature: structs.Temperature) -> None:
        # Note: this doesn't use MQTT data (previously it use to)
        self.previous_temperature = self.latest_temperature
        self.latest_temperature = temperature.temperature
        self.latest_temperature_at = temperature.timestamp

        if self.state == self.READY or self.state == self.INIT:
            self.latest_event = self.execute()

        return


class TemperatureAutomationJobContrib(TemperatureAutomationJob):
    automation_name: str


def start_temperature_automation(
    automation_name: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> TemperatureAutomationJob:
    from pioreactor.automations import temperature  # noqa: F401

    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)
    try:
        klass = available_temperature_automations[automation_name]
    except KeyError:
        raise KeyError(
            f"Unable to find {automation_name}. Available automations are {list( available_temperature_automations.keys())}"
        )

    if "skip_first_run" in kwargs:
        del kwargs["skip_first_run"]

    try:
        return klass(
            unit=unit,
            experiment=experiment,
            automation_name=automation_name,
            **kwargs,
        )

    except Exception as e:
        logger = create_logger("temperature_automation", experiment=experiment)
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


available_temperature_automations: dict[str, type[TemperatureAutomationJob]] = {}


@click.command(
    name="temperature_automation",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    help="set the automation of the system: silent, etc.",
    show_default=True,
    required=True,
)
@click.pass_context
def click_temperature_automation(ctx, automation_name):
    """
    Start an Temperature automation
    """
    with start_temperature_automation(
        automation_name=automation_name,
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    ) as ta:
        ta.block_until_disconnected()
