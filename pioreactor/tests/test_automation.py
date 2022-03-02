# -*- coding: utf-8 -*-
# test_automation.py
from __future__ import annotations

from pioreactor.structs import Automation


def test_str_representation():
    a = Automation(
        automation_name="test",
        args={"growth": 0.1, "intensity": "high", "value": True},
        automation_type="random",
    )

    assert str(a) == "test(growth=0.1, intensity=high, value=True)"
