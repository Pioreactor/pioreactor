# -*- coding: utf-8 -*-
# pump X ml every period (minute, 30min, hour, etc.)
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
        "dosing_volume_ml": {"datatype": "float", "unit": "mL", "settable": True},
    }

    def __init__(self, dosing_volume_ml, **kwargs) -> None:
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")

        self.logger.warning(
            "When using the fed-batch automation, no liquid is removed. Carefully monitor the level of liquid to avoid overflow!"
        )
        self.dosing_volume_ml = float(dosing_volume_ml)

    def execute(self):
        vol = self.add_media_to_bioreactor(
            ml=self.dosing_volume_ml,
            source_of_event=f"{self.job_name}:{self.automation_name}",
            unit=self.unit,
            experiment=self.experiment,
        )
        if vol != self.dosing_volume_ml:
            self.logger.warning("Under-dosed!")

        return events.AddMediaEvent(f"Added {vol} mL")
