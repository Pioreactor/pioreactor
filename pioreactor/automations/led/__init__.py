# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations import events
from pioreactor.automations.led.base import LEDAutomation


class Silent(LEDAutomation):

    automation_name = "silent"

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> events.Event:
        return events.NoEvent("no changes occur in Silent")
