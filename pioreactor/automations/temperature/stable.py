# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import UpdatedHeaterDC
from pioreactor.automations.temperature.base import TemperatureAutomationJob
from pioreactor.config import config
from pioreactor.utils import clamp
from pioreactor.utils.streaming_calculations import PID


class Stable(TemperatureAutomationJob):
    """
    Uses a PID controller to change the DC% to match a target temperature.
    """

    automation_name = "stable"
    published_settings = {
        "target_temperature": {"datatype": "float", "unit": "℃", "settable": True}
    }

    def __init__(self, target_temperature: float, **kwargs) -> None:
        super().__init__(**kwargs)
        assert target_temperature is not None, "target_temperature must be set"
        self.target_temperature = float(target_temperature)

        self.pid = PID(
            Kp=config.getfloat("temperature_automation.stable", "Kp"),
            Ki=config.getfloat("temperature_automation.stable", "Ki"),
            Kd=config.getfloat("temperature_automation.stable", "Kd"),
            setpoint=self.target_temperature,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
        )

    def execute(self) -> UpdatedHeaterDC:
        while not hasattr(self, "pid"):
            # sometimes when initializing, this execute can run before the subclasses __init__ is resolved.
            pass

        assert self.latest_temperature is not None
        output = self.pid.update(
            self.latest_temperature, dt=1
        )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
        self.update_heater_with_delta(output)
        return UpdatedHeaterDC(
            f"delta_dc={output}",
            data={
                "current_dc": None if self.parent is None else self.parent.heater_duty_cycle,
                "delta_dc": output,
            },
        )

    def set_target_temperature(self, value: float) -> None:
        value = float(value)
        if value > 50:
            self.logger.warning("Values over 50℃ are not supported. Setting to 50℃.")

        target_temperature = clamp(0, value, 50)
        self.target_temperature = target_temperature
        self.pid.set_setpoint(self.target_temperature)

        # when set_target_temperature is executed, and we wish to update the DC to some new value,
        # it's possible that it isn't updated immediately if set during the `evaluate` routine.
        if not self.is_heater_pwm_locked():
            assert self.latest_temperature is not None
            output = self.pid.update(
                self.latest_temperature, dt=1
            )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
            self.update_heater_with_delta(
                output / 2
            )  # the change occurs, on average, half way into the cycle.
