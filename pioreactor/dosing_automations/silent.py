# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events


class Silent(DosingAutomation):
    """
    Do nothing, ever. Just pass.
    """

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("never execute dosing events in Silent mode")
