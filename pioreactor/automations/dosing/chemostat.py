# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events


class Chemostat(DosingAutomation):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    key = "chemostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, volume=None, **kwargs):
        super(Chemostat, self).__init__(**kwargs)
        self.volume = float(volume)

    def execute(self) -> events.Event:
        volume_actually_cycled = self.execute_io_action(
            media_ml=self.volume, waste_ml=self.volume
        )
        return events.DilutionEvent(f"exchanged {volume_actually_cycled[0]}mL")
