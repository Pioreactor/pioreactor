# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.utils import local_persistant_storage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant. The algorithm should run at
    high frequency (every 5-10m) to react quickly to when the target OD is hit.

    This algo is very naive, and probably shouldn't be used.
    """

    automation_name = "turbidostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_od: float, volume: float, **kwargs) -> None:
        super(Turbidostat, self).__init__(**kwargs)

        with local_persistant_storage("pump_calibration") as cache:
            if "media_ml_calibration" not in cache:
                raise RuntimeError("Media pump calibration must be performed first.")
            elif "waste_ml_calibration" not in cache:
                raise RuntimeError("Waste pump calibration must be performed first.")

        self.target_od = float(target_od)
        self.volume = float(volume)

    def execute(self) -> events.Event:
        if self.latest_od >= self.target_od:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"latest OD={self.latest_od:.2f} >= target OD={self.target_od:.2f}"
            )
        else:
            return events.NoEvent(
                f"latest OD={self.latest_od:.2f} < target OD={self.target_od:.2f}"
            )
