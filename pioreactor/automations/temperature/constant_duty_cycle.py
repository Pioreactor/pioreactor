# -*- coding: utf-8 -*-
from pioreactor.automations.temperature.base import TemperatureAutomation


class ConstantDutyCycle(TemperatureAutomation):

    key = "constant_duty_cycle"
    published_settings = {
        "duty_cycle": {"datatype": "float", "unit": "%", "settable": True}
    }

    def __init__(self, duty_cycle, **kwargs):
        super(ConstantDutyCycle, self).__init__(**kwargs)
        self.set_duty_cycle(duty_cycle)

    def set_duty_cycle(self, dc):
        self.duty_cycle = float(dc)
        self.update_heater(dc)

    def execute(self):
        self.update_heater(self.duty_cycle)
