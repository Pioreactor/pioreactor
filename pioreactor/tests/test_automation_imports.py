# -*- coding: utf-8 -*-
# test_automation_imports
from __future__ import annotations

from pioreactor.background_jobs.temperature_automation import start_temperature_automation


def test_start_temperature_control() -> None:
    import importlib

    importlib.invalidate_caches()
    with start_temperature_automation(
        "thermostat", "test", "test_start_temperature_control", target_temperature=30
    ):
        pass
