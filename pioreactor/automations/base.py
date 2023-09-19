# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from pioreactor.automations import events
from pioreactor.background_jobs.subjobs import BackgroundSubJob


DISALLOWED_AUTOMATION_NAMES = {
    "config",
}


class AutomationJob(BackgroundSubJob):
    automation_name = "automation_job"

    def __init__(self, unit: str, experiment: str) -> None:
        super(AutomationJob, self).__init__(unit, experiment)

        if self.automation_name in DISALLOWED_AUTOMATION_NAMES:
            raise NameError(f"{self.automation_name} is not allowed.")

        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )

    def on_init_to_ready(self) -> None:
        self.start_passive_listeners()

    def execute(self) -> Optional[events.AutomationEvent]:
        """
        Overwrite in subclass
        """
        return events.NoEvent()
