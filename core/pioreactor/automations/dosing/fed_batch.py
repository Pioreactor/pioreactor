# -*- coding: utf-8 -*-
# pump X ml every period (minute, 30min, hour, etc.)
from typing import Any

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.background_jobs.dosing_automation import (
    check_pump_calibrations_and_pwm_channels_are_configured,
)


class FedBatch(DosingAutomationJob):
    """
    Useful for fed-batch automations
    """

    automation_name = "fed_batch"
    published_settings = {
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
        "dosing_volume_ml": {"datatype": "float", "unit": "mL", "settable": True},
    }

    def __init__(
        self,
        dosing_volume_ml: float | str,
        duration: float | str = 720,
        skip_first_run: bool | str | int = False,
        **kwargs: Any,
    ) -> None:
        check_pump_calibrations_and_pwm_channels_are_configured(("media_pump",))
        super().__init__(**kwargs)

        self.logger.warning(
            "When using the fed-batch automation, no liquid is removed. Carefully monitor the level of liquid to avoid overflow!"
        )
        self.dosing_volume_ml = float(dosing_volume_ml)
        self.run_every(duration, skip_first_run=skip_first_run, run_after_seconds=2.0)

    def execute(self) -> events.AddMediaEvent | events.NoEvent:
        projected_volume_ml = self.current_volume_ml + self.dosing_volume_ml
        if projected_volume_ml >= self.MAX_VIAL_VOLUME_TO_STOP:
            self.logger.error(
                f"Skipping fed-batch dose since {self.current_volume_ml:g} + {self.dosing_volume_ml} mL is beyond safety threshold {self.MAX_VIAL_VOLUME_TO_STOP} mL."
            )
            self.set_state(self.SLEEPING)
            return events.NoEvent("Skipped dosing to avoid overflow.")

        vol = self.add_media_to_bioreactor(
            ml=self.dosing_volume_ml,
            source_of_event=f"{self.job_name}:{self.automation_name}",
            unit=self.unit,
            experiment=self.experiment,
            mqtt_client=self.pub_client,
            logger=self.logger,
        )
        if vol != self.dosing_volume_ml:
            self.logger.warning("Under-dosed!")

        return events.AddMediaEvent(f"Added {vol} mL")
