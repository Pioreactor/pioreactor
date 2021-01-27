# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_algorithm import DosingAlgorithm
from pioreactor.dosing_algorithms import events


class Chemostat(DosingAlgorithm):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    def __init__(self, volume=None, duration=None, **kwargs):
        super(Chemostat, self).__init__(**kwargs)
        self.volume = float(volume)
        self.set_duration(duration)

    def execute(self, *args, **kwargs) -> events.Event:
        self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
        return events.DilutionEvent()
