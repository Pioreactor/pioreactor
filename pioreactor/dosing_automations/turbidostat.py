# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_algorithm import DosingAlgorithm
from pioreactor.dosing_algorithms import events


class Turbidostat(DosingAlgorithm):
    """
    Turbidostat mode - try to keep cell density constant. The algorithm should run at
    high frequency (every 5-10m) to react quickly to when the target OD is hit.

    This algo is very naive, and probably shouldn't be used.
    """

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(Turbidostat, self).__init__(**kwargs)
        self.target_od = float(target_od)
        self.volume = float(volume)

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od >= self.target_od:
            self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
            return events.DilutionEvent(
                f"latest OD={self.latest_od:.2f} >= target OD={self.target_od:.2f}"
            )
        else:
            return events.NoEvent(
                f"latest OD={self.latest_od:.2f} < target OD={self.target_od:.2f}"
            )
