# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.temperature.base import TemperatureAutomationJob


class ConstantDutyCycle(TemperatureAutomationJob):
    automation_name = "constant_duty_cycle"
    published_settings = {"duty_cycle": {"datatype": "float", "unit": "%", "settable": True}}

    def __init__(self, duty_cycle, **kwargs) -> None:
        super(ConstantDutyCycle, self).__init__(**kwargs)
        self.set_duty_cycle(float(duty_cycle))

    def set_duty_cycle(self, dc) -> None:
        self.duty_cycle = float(dc)
        self.update_heater(dc)

    def execute(self) -> None:
        self.update_heater(self.duty_cycle)
