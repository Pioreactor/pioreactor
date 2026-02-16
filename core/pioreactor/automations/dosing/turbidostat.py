# -*- coding: utf-8 -*-
from typing import cast
from typing import Optional

from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.estimators import load_active_estimator
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistent_storage


class Turbidostat(DosingAutomationJob):
    """
    Turbidostat mode - try to keep cell density constant by dosing whenever the target is surpassed.
    Note: this has a small "duration" param to run the algorithm-check constantly.
    """

    automation_name = "turbidostat"
    published_settings = {
        "exchange_volume_ml": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_biomass": {"datatype": "float", "settable": True, "unit": "OD/AU"},
        "biomass_signal": {"datatype": "string", "settable": False},
        "resolved_biomass_signal": {"datatype": "string", "settable": False},
        "duration": {"datatype": "float", "settable": False, "unit": "min"},
    }
    target_biomass = None
    biomass_signal = None

    def __init__(
        self,
        exchange_volume_ml: float | str,
        target_biomass: Optional[float | str] = None,
        biomass_signal: str | None = None,
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

        if biomass_signal is None:
            biomass_signal = config.get(
                "dosing_automation.turbidostat",
                "biomass_signal",
                fallback="auto",
            )

        self._set_biomass_signal(biomass_signal)
        self.target_biomass = float(target_biomass)

        self.exchange_volume_ml = float(exchange_volume_ml)

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

    @property
    def _od_angle(self) -> pt.PdAngle:
        angle = config["od_config.photodiode_channel"][self._od_channel]
        if angle in (None, "", REF_keyword):
            raise ValueError(f"No OD signal angle configured for channel {self._od_channel}.")
        return cast(pt.PdAngle, str(angle))

    def _has_active_od_fused_estimator(self) -> bool:
        try:
            return load_active_estimator(pt.OD_FUSED_DEVICE) is not None
        except Exception as e:
            self.logger.warning(
                "Unable to load active od_fused estimator for auto biomass signal selection: %s",
                e,
            )
            return False

    def _has_active_od_calibration_for_resolved_angle(self) -> bool:
        od_device = cast(pt.ODCalibrationDevices, f"od{self._od_angle}")
        try:
            return load_active_calibration(od_device) is not None
        except Exception as e:
            self.logger.warning(
                "Unable to load active OD calibration for device %s for auto biomass signal selection: %s",
                od_device,
                e,
            )
            return False

    def execute(self) -> Optional[events.DilutionEvent]:
        assert self.target_biomass is not None
        resolved_biomass_signal = self.resolved_biomass_signal
        latest_biomass = self.latest_biomass_value(resolved_biomass_signal, od_channel=self._od_channel)

        if latest_biomass >= self.target_biomass:
            latest_biomass_before_dosing = latest_biomass
            target_biomass_before_dosing = self.target_biomass

            results = self.execute_io_action(
                media_ml=self.exchange_volume_ml, waste_ml=self.exchange_volume_ml
            )

            data = {
                "latest_biomass": latest_biomass_before_dosing,
                "target_biomass": target_biomass_before_dosing,
                "resolved_biomass_signal": resolved_biomass_signal,
                "exchange_volume_ml": self.exchange_volume_ml,
                "volume_actually_moved_ml": results["media_ml"],
            }

            return events.DilutionEvent(
                f"Latest biomass ({resolved_biomass_signal}) = {latest_biomass_before_dosing:.2f} ≥ Target biomass = {target_biomass_before_dosing:.2f}; cycled {results['media_ml']:.2f} mL",
                data,
            )
        else:
            return None

    def set_target_biomass(self, new_target: float) -> None:
        self.target_biomass = float(new_target)

    @property
    def resolved_biomass_signal(self) -> str:
        if self.biomass_signal != "auto":
            return str(self.biomass_signal)

        if self._has_active_od_fused_estimator():
            return "od_fused"

        if self._has_active_od_calibration_for_resolved_angle():
            return "od"

        return "normalized_od"

    def set_biomass_signal(self, new_signal: str) -> None:
        self._set_biomass_signal(new_signal)

    def _set_biomass_signal(self, biomass_signal: str) -> None:
        allowed = ("auto", "normalized_od", "od_fused", "od")
        if biomass_signal not in allowed:
            raise ValueError(
                f"Unsupported biomass_signal={biomass_signal}. Use one of: {', '.join(allowed)}."
            )
        self.biomass_signal = biomass_signal
