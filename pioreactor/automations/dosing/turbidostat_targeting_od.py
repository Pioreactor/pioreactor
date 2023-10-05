# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistant_storage


class TurbidostatTargetingOD(DosingAutomationJob):
    """
    Try to keep cell density constant by dosing whenever the target_od is hit.
    This differs from `turbidostat` as this targets OD, not nOD.
    """

    automation_name = "turbidostat_targeting_od"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_od: float | str, volume: float | str, **kwargs) -> None:
        super().__init__(**kwargs)

        with local_persistant_storage("current_pump_calibration") as cache:
            if "media" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            if "waste" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")

        self.target_od = float(target_od)
        self.volume = float(volume)

    def execute(self) -> Optional[events.DilutionEvent]:
        if self.latest_od["2"] >= self.target_od:
            latest_od_before_dosing = self.latest_od["2"]
            target_od_before_dosing = self.target_od
            results = self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            media_moved = results["media_ml"]
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
