# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.automations.dosing.base import DosingAutomationJob


class Silent(DosingAutomationJob):
    """
    Do nothing, ever. Just pass.
    """

    automation_name = "silent"
    published_settings = {"duration": {"datatype": "float", "settable": True, "unit": "min"}}

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self):
        return
