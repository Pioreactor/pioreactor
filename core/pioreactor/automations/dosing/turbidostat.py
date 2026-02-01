# -*- coding: utf-8 -*-
from typing import cast
from typing import Optional

from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.config import config
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant by dosing whenever the target is surpassed.
    Note: this has a small "duration" param to run the algorithm-check constantly.
    """

    automation_name = "turbidostat"
    published_settings = {
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_biomass": {"datatype": "float", "settable": True},
        "biomass_signal": {"datatype": "string", "settable": True},
        "duration": {"datatype": "float", "settable": False, "unit": "min"},
    }
    target_biomass = None
    biomass_signal = None

    def __init__(
        self,
        exchange_volume_ml: float | str,
        target_biomass: Optional[float | str] = None,
        biomass_signal: str = "normalized_od",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste_pump" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")

        if target_biomass is None:
            raise ValueError("Provide a target biomass.")

        self._set_biomass_signal(biomass_signal)
        self.target_biomass = float(target_biomass)

        self.exchange_volume_ml = float(exchange_volume_ml)
        self.ema_od = ExponentialMovingAverage(
            config.getfloat("turbidostat.config", "od_smoothing_ema", fallback=0.5)
        )

    def set_duration(self, value: float | None):
        # force duration to always be 0.25 - we want to check often.
        super().set_duration(0.25)

    @property
    def _od_channel(self) -> pt.PdChannel:
        if not hasattr(self, "_resolved_od_channel"):
            self._resolved_od_channel = self._resolve_od_channel()
        return self._resolved_od_channel

    def _resolve_od_channel(self) -> pt.PdChannel:
        channels = config["od_config.photodiode_channel"]
        signal_channels: list[pt.PdChannel] = []
        for channel, angle in channels.items():
            if angle is None or angle == "" or angle == REF_keyword:
                continue
            signal_channels.append(cast(pt.PdChannel, channel))

        if len(signal_channels) == 1:
            return signal_channels[0]
        if len(signal_channels) > 1:
            selected_channel = min(signal_channels, key=lambda ch: int(ch))
            self.logger.warning(
                "Multiple OD signal channels detected (%s). Using channel %s. Prefer od_fused or normalized_od in this case.",
                ", ".join(signal_channels),
                selected_channel,
            )
            return selected_channel

        raise ValueError("No OD signal channels found in [od_config.photodiode_channel].")

    def execute(self) -> Optional[events.DilutionEvent]:
        assert self.target_biomass is not None
        latest_biomass = self.latest_biomass_value(self.biomass_signal, od_channel=self._od_channel)
        if self.biomass_signal in {"od", "od_fused"}:
            latest_biomass = self.ema_od.update(latest_biomass)

        if latest_biomass >= self.target_biomass:
            self.ema_od.clear()  # clear the ema so that we don't cause a second dosing to occur right after.
            latest_biomass_before_dosing = latest_biomass
            target_biomass_before_dosing = self.target_biomass

            results = self.execute_io_action(
                media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
            )

            data = {
                "latest_biomass": latest_biomass_before_dosing,
                "target_biomass": target_biomass_before_dosing,
                "biomass_signal": self.biomass_signal,
                "exchange_volume_ml": self.exchange_volume_ml,
                "volume_actually_moved_ml": results["media_ml"],
            }

            return events.DilutionEvent(
                f"Latest biomass ({self.biomass_signal}) = {latest_biomass_before_dosing:.2f} ≥ Target biomass = {target_biomass_before_dosing:.2f}; cycled {results['media_ml']:.2f} mL",
                data,
            )
        else:
            return None

    def set_target_biomass(self, new_target: float) -> None:
        self.target_biomass = float(new_target)

    def set_biomass_signal(self, new_signal: str) -> None:
        self._set_biomass_signal(new_signal)

    def _set_biomass_signal(self, biomass_signal: str) -> None:
        allowed = ("normalized_od", "od_fused", "od")
        if biomass_signal not in allowed:
            raise ValueError(f"Unsupported biomass_signal={biomass_signal}. Use one of: {', '.join(allowed)}.")
        self.biomass_signal = biomass_signal
