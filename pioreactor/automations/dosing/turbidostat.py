# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistant_storage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant by dosing whenever the target_normalized_od is hit.
    """

    automation_name = "turbidostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_normalized_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_normalized_od: float | str, volume: float | str, **kwargs) -> None:
        super().__init__(**kwargs)

        with local_persistant_storage("current_pump_calibration") as cache:
            if "media" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")

        self.target_normalized_od = float(target_normalized_od)
        self.volume = float(volume)

    def execute(self) -> Optional[events.DilutionEvent]:
        if self.latest_normalized_od >= self.target_normalized_od:
            latest_normalized_od_before_dosing = self.latest_normalized_od
            target_normalized_od_before_dosing = self.target_normalized_od
            results = self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            media_moved = results["media_ml"]
            return events.DilutionEvent(
                f"Latest Normalized OD = {latest_normalized_od_before_dosing:.2f} ≥ Target  nOD = {target_normalized_od_before_dosing:.2f}; cycled {media_moved:.2f} mL",
                {
                    "latest_normalized_od": latest_normalized_od_before_dosing,
                    "target_normalized_od": target_normalized_od_before_dosing,
                    "volume": media_moved,
                },
            )
        else:
            return None
