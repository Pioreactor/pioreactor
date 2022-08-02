# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistant_storage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant by dosing whenever the target_od is hit.
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
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste_ml_calibration" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")

        self.target_od = float(target_od)
        self.volume = float(volume)

    def execute(self) -> Optional[events.DilutionEvent]:
        if self.latest_od >= self.target_od:
            latest_od_before_dosing = self.latest_od
            target_od_before_dosing = self.target_od
            media_moved, _, _ = self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"Latest OD = {latest_od_before_dosing:.2f} ≥ Target OD = {target_od_before_dosing:.2f}; cycled {media_moved:.2f} mL",
                {
                    "latest_od": latest_od_before_dosing,
                    "target_od": target_od_before_dosing,
                    "volume": media_moved,
                },
            )
        else:
            return None
