# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events


class Chemostat(DosingAutomation):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    def __init__(self, volume=None, duration=None, **kwargs):
        super(Chemostat, self).__init__(**kwargs)
        self.volume = float(volume)
        self.set_duration(duration)

    def execute(self, *args, **kwargs) -> events.Event:
        self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
        return events.DilutionEvent()
