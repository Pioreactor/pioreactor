# -*- coding: utf-8 -*-
from pioreactor.automations.temperature.base import TemperatureAutomation


class Silent(TemperatureAutomation):

    automation_name = "silent"

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)
        self.update_heater(0)

    def execute(self) -> None:
        self.update_heater(0)
