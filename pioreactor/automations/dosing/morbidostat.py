# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistant_storage


class Morbidostat(DosingAutomationJob):
    """
    As defined in Toprak 2013., keep cell density below and threshold using chemical means. The conc.
    of the chemical is diluted slowly over time, allowing the microbes to recover.
    """

    automation_name = "morbidostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_normalized_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_normalized_od: float | str, volume: float | str, **kwargs):
        super(Morbidostat, self).__init__(**kwargs)

        with local_persistant_storage("current_pump_calibration") as cache:
            if "media" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")
            elif "alt_media" not in cache:
                raise CalibrationError("Alt media pump calibration must be performed first.")

        self.target_normalized_od = float(target_normalized_od)
        self.volume = float(volume)

    def execute(self) -> events.AutomationEvent:
        if self.previous_normalized_od is None:
            return events.NoEvent("skip first event to wait for OD readings.")
        elif (
            self.latest_normalized_od >= self.target_normalized_od
            and self.latest_normalized_od >= self.previous_normalized_od
        ):
            # if we are above the threshold, and growth rate is greater than dilution rate
            # the second condition is an approximation of this.
            self.execute_io_action(alt_media_ml=self.volume, waste_ml=self.volume)
            return events.AddAltMediaEvent(
                f"latest OD, {self.latest_normalized_od:.2f} >= Target OD, {self.target_normalized_od:.2f} and Latest OD, {self.latest_normalized_od:.2f} >= Previous OD, {self.previous_normalized_od:.2f}"
            )
        else:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"latest OD, {self.latest_normalized_od:.2f} < Target OD, {self.target_normalized_od:.2f} or Latest OD, {self.latest_normalized_od:.2f} < Previous OD, {self.previous_normalized_od:.2f}"
            )
