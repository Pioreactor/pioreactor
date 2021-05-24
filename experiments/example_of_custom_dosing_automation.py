# -*- coding: utf-8 -*-
import signal
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.whoami import get_unit_name, get_latest_experiment_name


class NaiveTurbidostat(DosingAutomation):

    key = "naive_turbidostat"

    def __init__(self, target_od, **kwargs):
        super(NaiveTurbidostat, self).__init__(**kwargs)
        self.target_od = target_od

    def execute(self):
        if self.latest_od > self.target_od:
            self.execute_io_action(media_ml=1.0, waste_ml=1.0)


if __name__ == "__main__":

    doser = NaiveTurbidostat(
        target_od=2.0, unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    while True:
        signal.pause()
        break
