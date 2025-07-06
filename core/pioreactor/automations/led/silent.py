# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations import events
from pioreactor.background_jobs.led_automation import LEDAutomationJob


class Silent(LEDAutomationJob):
    automation_name = "silent"
    published_settings = {"duration": {"datatype": "float", "settable": True, "unit": "min"}}

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> events.AutomationEvent:
        return events.NoEvent("no changes occur in Silent")
