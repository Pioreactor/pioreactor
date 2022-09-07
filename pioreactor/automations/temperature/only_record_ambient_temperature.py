# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.events import NoEvent
from pioreactor.automations.temperature.base import TemperatureAutomationJob


class OnlyRecordAmbientTemperature(TemperatureAutomationJob):

    automation_name = "only_record_ambient_temperature"

    def __init__(self, **kwargs) -> None:
        super(OnlyRecordAmbientTemperature, self).__init__(**kwargs)
        self.update_heater(0)

    def execute(self) -> NoEvent:
        self.update_heater(0)
        return NoEvent()
