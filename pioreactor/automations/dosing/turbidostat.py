# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import cast
from typing import Optional

from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.config import config
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant by dosing whenever the target is surpassed
    """

    automation_name = "turbidostat"
    published_settings = {
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_normalized_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "target_od": {"datatype": "float", "settable": True, "unit": "OD"},
    }
    target_od = None
    target_normalized_od = None

    def __init__(
        self,
        exchange_volume_ml: float | str,
        target_normalized_od: Optional[float | str] = None,
        target_od: Optional[float | str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste_pump" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")

        if target_normalized_od is not None and target_od is not None:
            raise ValueError("Only provide target nOD or target OD, not both.")
        elif target_normalized_od is None and target_od is None:
            raise ValueError("Provide a target nOD or target OD.")

        if target_normalized_od is not None:
            self.target_normalized_od = float(target_normalized_od)
        elif target_od is not None:
            self.target_od = float(target_od)

        self.exchange_volume_ml = float(exchange_volume_ml)
        self.ema_od = ExponentialMovingAverage(
            config.getfloat("turbidostat.config", "od_smoothing_ema", fallback=0.5)
        )

    @property
    def is_targeting_nOD(self) -> bool:
        return self.target_normalized_od is not None

    @property
    def _od_channel(self) -> pt.PdChannel:
        return cast(
            pt.PdChannel,
            config.get("turbidostat.config", "signal_channel", fallback="2"),
        )

    def _handle_pump_malfunction(self, od_pre_timestamp: datetime, od_pre: float) -> None:
        """Detects pump malfunction by comparing the post-dosing OD to its predicted value."""
        if not config.getboolean(
            "dosing_automation.config", "experimental_detect_pump_malfunction", fallback=False
        ):
            return
        od_channel = self._od_channel
        od_post_timestamp = self.latest_od_at
        od_post = self.latest_od[od_channel]

        # only check if new OD reading seen
        if od_post_timestamp != od_pre_timestamp:
            tol = config.getfloat(
                "dosing_automation.config", "experimental_pump_malfunction_tolerance", fallback=0.2
            )
            predicted_od_post = od_pre * self.exchange_volume_ml / self.current_volume_ml
            lower_bound = (1.0 - tol) * predicted_od_post
            upper_bound = (1.0 + tol) * predicted_od_post
            if not (lower_bound <= od_post <= upper_bound):
                pct = int(tol * 100)
                self.logger.info(
                    f"OD after dosing is not within ±{pct}% of predicted: {od_post} vs {predicted_od_post}"
                )
                self.set_state(self.SLEEPING)

    def execute(self) -> Optional[events.DilutionEvent]:
        if self.is_targeting_nOD:
            return self._execute_target_nod()
        else:
            return self._execute_target_od()

    def set_target_normalized_od(self, new_target: float) -> None:
        if not self.is_targeting_nOD:
            self.logger.warning("You are currently targeting OD, and can only change that.")
        else:
            self.target_normalized_od = float(new_target)

    def set_target_od(self, new_target: float) -> None:
        if self.is_targeting_nOD:
            self.logger.warning("You are currently targeting nOD, and can only change that.")
        else:
            self.target_od = float(new_target)

    def _execute_target_od(self) -> Optional[events.DilutionEvent]:
        assert self.target_od is not None
        smoothed_od = self.ema_od.update(self.latest_od[self._od_channel])
        if smoothed_od >= self.target_od:
            self.ema_od.clear()  # clear the ema so that we don't cause a second dosing to occur right after.
            latest_od_before_dosing = smoothed_od
            target_od_before_dosing = self.target_od
            od_pre_timestamp, od_pre = self.latest_od_at, self.latest_od[self._od_channel]

            results = self.execute_io_action(
                media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
            )
            media_moved = results["media_ml"]

            self._handle_pump_malfunction(od_pre_timestamp, od_pre)

            return events.DilutionEvent(
                f"Latest OD = {latest_od_before_dosing:.2f} ≥ Target OD = {target_od_before_dosing:.2f}; cycled {media_moved:.2f} mL",
                {
                    "latest_od": latest_od_before_dosing,
                    "target_od": target_od_before_dosing,
                    "exchange_volume_ml": media_moved,
                },
            )
        else:
            return None

    def _execute_target_nod(self) -> Optional[events.DilutionEvent]:
        assert self.target_normalized_od is not None
        if self.latest_normalized_od >= self.target_normalized_od:
            latest_normalized_od_before_dosing = self.latest_normalized_od
            target_normalized_od_before_dosing = self.target_normalized_od
            od_pre_timestamp, od_pre = self.latest_od_at, self.latest_od[self._od_channel]

            results = self.execute_io_action(
                media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
            )
            media_moved = results["media_ml"]

            self._handle_pump_malfunction(od_pre_timestamp, od_pre)

            return events.DilutionEvent(
                f"Latest Normalized OD = {latest_normalized_od_before_dosing:.2f} ≥ Target  nOD = {target_normalized_od_before_dosing:.2f}; cycled {media_moved:.2f} mL",
                {
                    "latest_normalized_od": latest_normalized_od_before_dosing,
                    "target_normalized_od": target_normalized_od_before_dosing,
                    "exchange_volume_ml": media_moved,
                },
            )
        else:
            return None
