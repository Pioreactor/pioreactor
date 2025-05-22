# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import UpdatedHeaterDC
from pioreactor.background_jobs.temperature_automation import classproperty
from pioreactor.background_jobs.temperature_automation import is_20ml_v1
from pioreactor.background_jobs.temperature_automation import TemperatureAutomationJob
from pioreactor.config import config
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.streaming_calculations import PID


class Thermostat(TemperatureAutomationJob):
    """
    Uses a PID controller to change the DC% to match a target temperature.
    """

    automation_name = "thermostat"
    published_settings = {"target_temperature": {"datatype": "float", "unit": "℃", "settable": True}}

    def __init__(self, target_temperature: float | str, **kwargs) -> None:
        super().__init__(**kwargs)
        assert target_temperature is not None, "target_temperature must be set"

        self.pid = PID(
            Kp=config.getfloat("temperature_automation.thermostat", "Kp"),
            Ki=config.getfloat("temperature_automation.thermostat", "Ki"),
            Kd=config.getfloat("temperature_automation.thermostat", "Kd"),
            setpoint=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
            output_limits=(-25, 25),  # avoid whiplashing
            pub_client=self.pub_client,
        )

        self.set_target_temperature(target_temperature)

    def on_init_to_ready(self):
        super().on_init_to_ready()
        if not is_pio_job_running("stirring"):
            self.logger.warning("It's recommended to have stirring on when using the thermostat.")

    def _clamp_target_temperature(self, target_temperature: float) -> float:
        if target_temperature > self.MAX_TARGET_TEMP:
            self.logger.warning(
                f"Values over {self.MAX_TARGET_TEMP}℃ are not supported. Setting to {self.MAX_TARGET_TEMP}℃."
            )

        return clamp(0.0, target_temperature, self.MAX_TARGET_TEMP)

    def on_disconnected(self) -> None:
        super().on_disconnected()
        self.pid.clean_up()

    def execute(self) -> UpdatedHeaterDC:
        while not hasattr(self, "pid"):
            # sometimes when initializing, this execute can run before the subclasses __init__ is resolved.
            pass

        assert self.latest_temperature is not None
        output = self.pid.update(
            self.latest_temperature, dt=1
        )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
        # TOOD: 1 kinda sucks, since it's possible there is a quick succession of messages, i.e. from a network disconnect -> reconnect.
        self.update_heater_with_delta(output)
        self.logger.debug(f"PID output = {output}")

        return UpdatedHeaterDC(
            f"delta_dc={output}",
            data={
                "current_dc": self.heater_duty_cycle,
                "delta_dc": output,
                "target_temperature": self.target_temperature,
                "latest_temperature": self.latest_temperature,
            },
        )

    def set_target_temperature(self, target_temperature: float | str) -> None:
        """
        Parameters
        ------------

        target_temperature: float
            the new target temperature
        """
        target_temperature = float(target_temperature)
        self.target_temperature = self._clamp_target_temperature(target_temperature)
        self.pid.set_setpoint(self.target_temperature)

    @classproperty
    def MAX_TARGET_TEMP(cls) -> float:
        return 63.0 if is_20ml_v1() else 78.0
