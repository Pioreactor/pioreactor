# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import NoEvent
from pioreactor.automations.temperature.base import TemperatureAutomationJob


class Silent(TemperatureAutomationJob):

    automation_name = "silent"

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)
        self.update_heater(0)

    def execute(self) -> NoEvent:
        self.update_heater(0)
        return NoEvent()
