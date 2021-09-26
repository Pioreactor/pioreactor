# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events


class Morbidostat(DosingAutomation):
    """
    As defined in Toprak 2013., keep cell density below and threshold using chemical means. The conc.
    of the chemical is diluted slowly over time, allowing the microbes to recover.
    """

    key = "morbidostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(Morbidostat, self).__init__(**kwargs)
        self.target_od = float(target_od)
        self.volume = float(volume)

    def execute(self) -> events.Event:
        if self.previous_od is None:
            return events.NoEvent("skip first event to wait for OD readings.")
        elif self.latest_od >= self.target_od and self.latest_od >= self.previous_od:
            # if we are above the threshold, and growth rate is greater than dilution rate
            # the second condition is an approximation of this.
            self.execute_io_action(alt_media_ml=self.volume, waste_ml=self.volume)
            return events.AltMediaEvent(
                f"latest OD, {self.latest_od:.2f} >= Target OD, {self.target_od:.2f} and Latest OD, {self.latest_od:.2f} >= Previous OD, {self.previous_od:.2f}"
            )
        else:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"latest OD, {self.latest_od:.2f} < Target OD, {self.target_od:.2f} or Latest OD, {self.latest_od:.2f} < Previous OD, {self.previous_od:.2f}"
            )
