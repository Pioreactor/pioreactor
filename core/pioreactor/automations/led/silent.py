# -*- coding: utf-8 -*-
from typing import Any

from pioreactor import structs
from pioreactor.automations import events
from pioreactor.background_jobs.led_automation import LEDAutomationJob


class Silent(LEDAutomationJob):
    automation_name = "silent"
    published_settings: dict = {}

    def __init__(self, **kwargs: Any) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> structs.AutomationEvent:
        return events.NoEvent("no changes occur in Silent")
