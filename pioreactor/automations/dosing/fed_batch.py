# -*- coding: utf-8 -*-
# pump X ml every period (minute, 30min, hour, etc.)
from __future__ import annotations

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage


class FedBatch(DosingAutomationJob):
    """
    Useful for fed-batch automations
    """

    automation_name = "fed_batch"
    published_settings = {
        "volume": {"datatype": "float", "unit": "mL", "settable": True},
    }

    def __init__(self, volume, **kwargs):
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")

        self.logger.warning(
            "When using the fed-batch automation, no liquid is removed. Carefully monitor the level of liquid to avoid overflow!"
        )
        self.volume = float(volume)

    def execute(self):
        vol = self.add_media_to_bioreactor(
            ml=self.volume,
            source_of_event=f"{self.job_name}:{self.automation_name}",
            unit=self.unit,
            experiment=self.experiment,
        )
        if vol != self.volume:
            self.logger.warning("Under-dosed!")

        return events.AddMediaEvent(f"Added {vol} mL")
