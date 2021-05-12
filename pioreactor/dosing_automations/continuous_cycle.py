# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.actions.add_media import add_media


class ContinuousCycle(DosingAutomation):
    """
    Useful for using the Pioreactor as an inline sensor.
    """

    def __init__(self, **kwargs):
        super(ContinuousCycle, self).__init__(**kwargs)

    def run(self):
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return

        elif self.state != self.READY:
            time.sleep(5)
            return self.run()

        else:
            return self.execute()

    def execute(self, *args, **kwargs):
        add_media(
            continuously=True,
            duty_cycle=100,
            source_of_event=f"{self.job_name}:{self.__class__.__name__}",
            unit=self.unit,
            experiment=self.experiment,
        )
