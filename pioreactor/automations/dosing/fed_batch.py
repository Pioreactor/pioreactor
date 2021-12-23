# -*- coding: utf-8 -*-

# pump X ml every period (minute, 30min, hour, etc.)

from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events
from pioreactor.actions.add_media import add_media


class FedBatch(DosingAutomation):
    """
    Useful for fed-batch automations
    """

    automation_name = "fed_batch"
    published_settings = {
        "volume": {"datatype": "float", "unit": "mL", "settable": True},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, volume, **kwargs):
        super(FedBatch, self).__init__(**kwargs)
        self.volume = float(volume)

    def execute(self):
        vol = add_media(
            ml=self.volume,
            source_of_event=f"{self.job_name}:{self.automation_name}",
            unit=self.unit,
            experiment=self.experiment,
        )
        if vol != self.volume:
            self.logger.warning("under-dosed!")

        return events.AddMediaEvent(f"Added {vol}mL")
