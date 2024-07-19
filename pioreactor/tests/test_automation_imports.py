# -*- coding: utf-8 -*-
from __future__ import annotations


def test_start_temperature_automation() -> None:
    import importlib

    importlib.invalidate_caches()

    from pioreactor.background_jobs.temperature_automation import start_temperature_automation

    with start_temperature_automation(
        "thermostat", "test", "test_start_temperature_automation", target_temperature=30
    ):
        pass
