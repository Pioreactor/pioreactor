# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import NoEvent
from pioreactor.automations.temperature.base import TemperatureAutomationJob


class OnlyRecordTemperature(TemperatureAutomationJob):
    automation_name = "only_record_temperature"

    def __init__(self, **kwargs) -> None:
        super(OnlyRecordTemperature, self).__init__(**kwargs)
        self.update_heater(0)

    def execute(self) -> NoEvent:
        if self.heater_duty_cycle != 0:
            self.update_heater(0)
        return NoEvent()
