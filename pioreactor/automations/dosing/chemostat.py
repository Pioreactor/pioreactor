# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import cast

from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.config import config
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage


class Chemostat(DosingAutomationJob):
    """
    Chemostat mode - try to keep [nutrient] constant.
    """

    automation_name = "chemostat"
    published_settings = {
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
    }

    def __init__(self, exchange_volume_ml: float | str, **kwargs) -> None:
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media and waste pump calibration must be performed first.")
            elif "waste_pump" not in cache:
                raise CalibrationError("Media and waste pump calibration must be performed first.")

        self.exchange_volume_ml = float(exchange_volume_ml)

    def execute(self) -> events.DilutionEvent:
        detect = config.getboolean(
            "dosing_automation.config", "experimental_detect_pump_malfunction", fallback=False
        )
        if detect:
            od_channel = cast(
                pt.PdChannel,
                config.get("turbidostat.config", "signal_channel", fallback="2"),
            )
            od_pre_timestamp = self.latest_od_at
            od_pre = self.latest_od[od_channel]
            predicted_od_post = od_pre * self.exchange_volume_ml / self.current_volume_ml

        volume_actually_cycled = self.execute_io_action(
            media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
        )

        if detect:
            od_post_timestamp = self.latest_od_at
            od_post = self.latest_od[od_channel]
            # only check if new OD reading seen
            if od_post_timestamp != od_pre_timestamp:
                if not (0.80 * predicted_od_post <= od_post <= 1.20 * predicted_od_post):
                    self.logger.info(
                        f"OD after dosing is not within 20% of predicted: {od_post} vs {predicted_od_post}"
                    )
                    self.set_state(self.SLEEPING)

        return events.DilutionEvent(
            f"exchanged {volume_actually_cycled['media_ml']}mL",
            data={"volume_actually_cycled": volume_actually_cycled["waste_ml"]},
        )
