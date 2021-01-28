# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_algorithm import DosingAlgorithm
from pioreactor.dosing_algorithms import events


class Silent(DosingAlgorithm):
    """
    Do nothing, ever. Just pass.
    """

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("never execute dosing events in Silent mode")
