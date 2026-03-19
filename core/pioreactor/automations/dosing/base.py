# -*- coding: utf-8 -*-
# here for backwards compatible reasons
from pioreactor.background_jobs.dosing_automation import DosingAutomationJob as DosingAutomationJob
from pioreactor.background_jobs.dosing_automation import (
    DosingAutomationJobContrib as DosingAutomationJobContrib,
)

__all__ = ["DosingAutomationJob", "DosingAutomationJobContrib"]
