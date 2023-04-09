# -*- coding: utf-8 -*-
from __future__ import annotations

from .light_dark_cycle import LightDarkCycle
from pioreactor.automations import events
from pioreactor.automations.led.base import LEDAutomationJob


class Silent(LEDAutomationJob):
    automation_name = "silent"

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> events.AutomationEvent:
        return events.NoEvent("no changes occur in Silent")
