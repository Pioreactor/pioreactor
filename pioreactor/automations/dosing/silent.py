# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events


class Silent(DosingAutomation):
    """
    Do nothing, ever. Just pass.
    """

    automation_name = "silent"
    published_settings = {
        "duration": {"datatype": "float", "settable": True, "unit": "min"}
    }

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> events.Event:
        return events.NoEvent("never execute dosing events in Silent mode")
