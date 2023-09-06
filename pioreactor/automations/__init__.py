# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.background_jobs.subjobs import BackgroundSubJob

DISALLOWED_AUTOMATION_NAMES = {
    "config",
}


class BaseAutomationJob(BackgroundSubJob):
    automation_name = "base_automation_job"

    def __init__(self, unit: str, experiment: str):
        super(BaseAutomationJob, self).__init__(unit, experiment)

        if self.automation_name in DISALLOWED_AUTOMATION_NAMES:
            raise NameError(f"{self.automation_name} is not allowed.")

        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )
