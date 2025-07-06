# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
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

    @property
    def _od_channel(self) -> pt.PdChannel:
        return cast(
            pt.PdChannel,
            config.get("turbidostat.config", "signal_channel", fallback="2"),
        )

    def _handle_pump_malfunction(self, od_pre_ts: datetime, od_pre: float) -> None:
        """Detects pump malfunction by comparing the post-dosing OD to its predicted value."""
        if not config.getboolean(
            "dosing_automation.config", "experimental_detect_pump_malfunction", fallback=False
        ):
            return
        od_post_ts = self.latest_od_at
        od_post = self.latest_od[self._od_channel]

        # only check if new OD reading seen
        if od_post_ts != od_pre_ts:
            tol = config.getfloat("dosing_automation.config", "pump_malfunction_tolerance", fallback=0.2)
            predicted = od_pre * self.exchange_volume_ml / self.current_volume_ml
            lower = (1.0 - tol) * predicted
            upper = (1.0 + tol) * predicted
            if not (lower <= od_post <= upper):
                pct = int(tol * 100)
                self.logger.info(
                    f"OD after dosing is not within ±{pct}% of predicted: {od_post} vs {predicted}"
                )
                self.set_state(self.SLEEPING)

    def execute(self) -> events.DilutionEvent:
        """
        Executes dilution step and optionally detects pump malfunction by comparing expected OD change.
        """
        detect = config.getboolean(
            "dosing_automation.config", "experimental_detect_pump_malfunction", fallback=False
        )
        od_pre_ts: datetime | None = None
        od_pre: float | None = None
        if detect:
            od_pre_ts = self.latest_od_at
            od_pre = self.latest_od[self._od_channel]

        volume_actually_cycled = self.execute_io_action(
            media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
        )

        if detect and od_pre_ts is not None and od_pre is not None:
            self._handle_pump_malfunction(od_pre_ts, od_pre)

        return events.DilutionEvent(
            f"exchanged {volume_actually_cycled['media_ml']}mL",
            data={"volume_actually_cycled": volume_actually_cycled["waste_ml"]},
        )
