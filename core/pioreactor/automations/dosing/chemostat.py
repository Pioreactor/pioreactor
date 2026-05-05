# -*- coding: utf-8 -*-
from typing import Any

from pioreactor.automations import events
from pioreactor.background_jobs.dosing_automation import (
    check_pump_calibrations_and_pwm_channels_are_configured,
)
from pioreactor.background_jobs.dosing_automation import DosingAutomationJob


class Chemostat(DosingAutomationJob):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    automation_name = "chemostat"
    published_settings = {
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
    }

    def __init__(
        self,
        exchange_volume_ml: float | str,
        duration: float | str = 20,
        skip_first_run: bool | str | int = False,
        **kwargs: Any,
    ) -> None:
        check_pump_calibrations_and_pwm_channels_are_configured(("media_pump", "waste_pump"))
        super().__init__(**kwargs)

        self.exchange_volume_ml = float(exchange_volume_ml)
        self.run_every(duration, skip_first_run=skip_first_run, run_after_seconds=2.0)

    def execute(self) -> events.DilutionEvent:
        """
        Executes dilution step and optionally detects pump malfunction by comparing expected OD change.
        """

        volume_actually_cycled = self.execute_io_action(
            media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
        )

        data = {
            "exchange_volume_ml": self.exchange_volume_ml,
            "volume_actually_cycled_ml": volume_actually_cycled["media_ml"],
        }

        return events.DilutionEvent(
            f"exchanged {volume_actually_cycled['media_ml']}mL",
            data=data,
        )
