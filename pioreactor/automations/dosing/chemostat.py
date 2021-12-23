# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events
from pioreactor.utils import local_persistant_storage


class Chemostat(DosingAutomation):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    automation_name = "chemostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, volume=None, **kwargs):
        super(Chemostat, self).__init__(**kwargs)

        with local_persistant_storage("pump_calibration") as cache:
            if "media_ml_calibration" not in cache:
                raise RuntimeError("Media pump calibration must be performed first.")
            elif "waste_ml_calibration" not in cache:
                raise RuntimeError("Waste pump calibration must be performed first.")

        self.volume = float(volume)

    def execute(self) -> events.Event:
        volume_actually_cycled = self.execute_io_action(
            media_ml=self.volume, waste_ml=self.volume
        )
        return events.DilutionEvent(f"exchanged {volume_actually_cycled[0]}mL")
