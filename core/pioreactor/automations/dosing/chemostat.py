# -*- coding: utf-8 -*-
from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage


class Chemostat(DosingAutomationJob):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    automation_name = "chemostat"
    published_settings = {
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
    }

    def __init__(self, exchange_volume_ml: float | str, **kwargs) -> None:
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media and waste pump calibration must be performed first.")
            elif "waste_pump" not in cache:
                raise CalibrationError("Media and waste pump calibration must be performed first.")

        self.exchange_volume_ml = float(exchange_volume_ml)

    def execute(self) -> events.DilutionEvent:
        """
        Executes dilution step and optionally detects pump malfunction by comparing expected OD change.
        """

        volume_actually_cycled = self.execute_io_action(
            media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
        )

        data = {
            "exchange_volume_ml": self.exchange_volume_ml,
            "volume_actually_cycled_ml": volume_actually_cycled["media_ml"],
        }

        return events.DilutionEvent(
            f"exchanged {volume_actually_cycled['media_ml']}mL",
            data=data,
        )
