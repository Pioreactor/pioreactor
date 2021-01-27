# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_algorithm import DosingAlgorithm
from pioreactor.dosing_algorithms import events


class Chemostat(DosingAlgorithm):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    def __init__(self, volume=None, **kwargs):
        super(Chemostat, self).__init__(**kwargs)
        self.volume = float(volume)

    def execute(self, *args, **kwargs) -> events.Event:
        self.execute_io_action(media_ml=self.volume, waste_ml=self.volume)
