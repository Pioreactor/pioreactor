# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation


class Silent(DosingAutomation):
    """
    Do nothing, ever. Just pass.
    """

    automation_name = "silent"
    published_settings = {
        "duration": {"datatype": "float", "settable": True, "unit": "min"}
    }

    def __init__(self, **kwargs) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> None:
        return
