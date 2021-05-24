# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events


class Silent(DosingAutomation):
    """
    Do nothing, ever. Just pass.
    """

    key = "silent"

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def run(self):
        # TODO: this is techdebt. I wonder if *_automations should declare
        # what they require in their __init__ or top-level, ex:
        # requires = ['growth_rate', 'od']
        # and the parent `run` method controls how to handle this.
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return

        elif self.state != self.READY:
            time.sleep(5)
            return self.run()

        else:
            event = self.execute()
            self.latest_event = event
            return event

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("never execute dosing events in Silent mode")
