# -*- coding: utf-8 -*-
from contextlib import suppress
from datetime import datetime
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
from pioreactor.temperature_inference import create_temperature_inference_estimator
from pioreactor.temperature_inference import infer_temperature_legacy_20_1_0
from pioreactor.temperature_inference import infer_temperature_legacy_20_2_0
from pioreactor.temperature_providers import create_temperature_provider
from pioreactor.temperature_providers import TemperatureProvider
from pioreactor.temperature_providers import TemperatureProviderContext
from pioreactor.utils import clamp
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import whoami
from pioreactor.utils.pwm import PWM
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime
from pioreactor.whoami import get_pioreactor_model


class classproperty(property):
    def __get__(self, obj, objtype=None):
        return self.fget(objtype)


def is_20ml_v1() -> bool:
    return get_pioreactor_model().model_name.startswith(
        "pioreactor_20ml"
    ) and get_pioreactor_model().model_version == (1, 0)


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
        return get_pioreactor_model().max_temp_to_reduce_heating

    @classproperty
    def MAX_TEMP_TO_DISABLE_HEATING(cls) -> float:
        return get_pioreactor_model().max_temp_to_disable_heating

    @classproperty
    def MAX_TEMP_TO_SHUTDOWN(cls) -> float:
        return get_pioreactor_model().max_temp_to_shutdown

    @classproperty
    def INFERENCE_N_SAMPLES(cls) -> int:
        return 29 if is_20ml_v1() else 21

    @classproperty
    def INFERENCE_EVERY_N_SECONDS(cls) -> float:
        return 225.0 if is_20ml_v1() else 200.0

    latest_temperature = None
    previous_temperature = None
    latest_temperature_at: datetime
    previous_temperature_at: Optional[datetime] = None
    latest_temperature_dt: float = 1.0

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
        unit: pt.Unit,
        experiment: pt.Experiment,
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

        self._exit_event = Event()

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

        self.heating_pcb_tmp_driver = TMP1075(address=hardware.get_temp_address())
        model = get_pioreactor_model()
        inference_estimator_name = config.get(
            "temperature_automation.config",
            "inference_estimator",
            fallback="legacy",
        )
        self._temperature_inference_estimator = create_temperature_inference_estimator(
            inference_estimator_name,
            model=model,
            logger=self.logger,
        )
        self._temperature_provider: TemperatureProvider = create_temperature_provider(
            config.get("temperature_automation.config", "temperature_provider", fallback="legacy_decay"),
            TemperatureProviderContext(
                logger=self.logger,
                pwm=self.pwm,
                inference_estimator=self._temperature_inference_estimator,
                read_external_temperature=self.read_external_temperature,
                update_heater=self._update_heater,
                get_heater_duty_cycle=lambda: self.heater_duty_cycle,
                should_exit=self._exit_event.is_set,
                get_room_temperature=self._get_room_temperature,
                inference_n_samples=self.INFERENCE_N_SAMPLES,
                inference_samples_every_t_seconds=self.INFERENCE_SAMPLES_EVERY_T_SECONDS,
                inference_every_n_seconds=self.INFERENCE_EVERY_N_SECONDS,
            ),
        )

        self.read_external_temperature_timer = RepeatedTimer(
            53,
            self.read_external_temperature,
            job_name=self.job_name,
            run_immediately=False,
            logger=self.logger,
        ).start()

        self.publish_temperature_timer = RepeatedTimer(
            self._temperature_provider.schedule.interval_seconds,
            self.infer_temperature,
            job_name=self.job_name,
            run_after=self._temperature_provider.schedule.run_after_seconds,
            run_immediately=self._temperature_provider.schedule.run_immediately,
        ).start()

        self.latest_temperature_at = current_utc_datetime()
        self.previous_temperature_at = None
        self.latest_temperature_dt = 1.0

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
        heater_channel = hardware.get_heater_pwm_channel()
        pin = hardware.get_pwm_to_pin_map()[heater_channel]
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
        try:
            inferred_temperature = self._temperature_provider.infer_temperature()
            if inferred_temperature is None:
                return

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
        return infer_temperature_legacy_20_1_0(features)

    @staticmethod
    def approximate_temperature_20_2_0(features: dict[str, Any]) -> float:
        return infer_temperature_legacy_20_2_0(features)

    def _set_latest_temperature(self, temperature: structs.Temperature) -> None:
        # Note: this doesn't use MQTT data (previously it use to)
        self.previous_temperature = self.latest_temperature
        self.previous_temperature_at = self.latest_temperature_at
        self.latest_temperature = temperature.temperature
        self.latest_temperature_at = temperature.timestamp
        if self.previous_temperature is None or self.previous_temperature_at is None:
            self.latest_temperature_dt = 1.0
        else:
            elapsed_seconds = (self.latest_temperature_at - self.previous_temperature_at).total_seconds()
            nominal_interval = max(0.001, float(self._temperature_provider.schedule.interval_seconds))
            self.latest_temperature_dt = max(0.001, elapsed_seconds / nominal_interval)

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
            f"Unable to find {automation_name}. Available automations are {list(available_temperature_automations.keys())}"
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
