# -*- coding: utf-8 -*-
from typing import Any

from pioreactor.automations.dosing.base import DosingAutomationJob


class Silent(DosingAutomationJob):
    """
    Do nothing, ever. Just pass.
    """

    automation_name = "silent"
    published_settings: dict = {}

    def __init__(self, **kwargs: Any) -> None:
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> None:
        return
