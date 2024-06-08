# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import UpdatedHeaterDC
from pioreactor.automations.temperature.base import TemperatureAutomationJob
from pioreactor.config import config
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.streaming_calculations import PID
from pioreactor.whoami import get_pioreactor_version


class Thermostat(TemperatureAutomationJob):
    """
    Uses a PID controller to change the DC% to match a target temperature.
    """

    if get_pioreactor_version() == (1, 0):
        MAX_TARGET_TEMP = 50
    else:
        MAX_TARGET_TEMP = 70

    automation_name = "thermostat"
    published_settings = {"target_temperature": {"datatype": "float", "unit": "℃", "settable": True}}

    def __init__(self, target_temperature: float | str, **kwargs) -> None:
        super().__init__(**kwargs)
        assert target_temperature is not None, "target_temperature must be set"
        self.target_temperature = float(target_temperature)

        self.pid = PID(
            Kp=config.getfloat("temperature_automation.thermostat", "Kp"),
            Ki=config.getfloat("temperature_automation.thermostat", "Ki"),
            Kd=config.getfloat("temperature_automation.thermostat", "Kd"),
            setpoint=self.target_temperature,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
            output_limits=(-25, 25),  # avoid whiplashing
        )

        if not is_pio_job_running("stirring"):
            self.logger.warning("It's recommended to have stirring on when using the thermostat.")

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
            },
        )

    def set_target_temperature(self, target_temperature: float) -> None:
        """

        Parameters
        ------------

        target_temperature: float
            the new target temperature
        update_dc_now: bool
            if possible, update the DC% to approach the new target temperature

        """
        target_temperature = float(target_temperature)
        if target_temperature > self.MAX_TARGET_TEMP:
            self.logger.warning(
                f"Values over {self.MAX_TARGET_TEMP}℃ are not supported. Setting to {self.MAX_TARGET_TEMP}℃."
            )

        target_temperature = clamp(0, target_temperature, self.MAX_TARGET_TEMP)
        self.target_temperature = target_temperature
        self.pid.set_setpoint(self.target_temperature)
