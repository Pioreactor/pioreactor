# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import suppress

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.config import config
from pioreactor.exc import CalibrationError
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.streaming_calculations import PID


class PIDMorbidostat(DosingAutomationJob):
    """
    As defined in Zhong 2020
    """

    VIAL_VOLUME = config.getfloat("bioreactor", "max_volume_ml", fallback=14)
    automation_name = "pid_morbidostat"
    published_settings = {
        "volume": {"datatype": "float", "settable": True, "unit": "mL"},
        "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "target_growth_rate": {"datatype": "float", "settable": True, "unit": "h⁻¹"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_growth_rate: float | str, target_od: float | str, **kwargs):
        super(PIDMorbidostat, self).__init__(**kwargs)
        assert target_od is not None, "`target_od` must be set"
        assert target_growth_rate is not None, "`target_growth_rate` must be set"

        with local_persistant_storage("current_pump_calibration") as cache:
            if "media" not in cache:
                raise CalibrationError("Media pump calibration must be performed first.")
            elif "waste" not in cache:
                raise CalibrationError("Waste pump calibration must be performed first.")
            elif "alt_media" not in cache:
                raise CalibrationError("Alt-Media pump calibration must be performed first.")

        self.set_target_growth_rate(target_growth_rate)
        self.target_od = float(target_od)

        Kp = config.getfloat("dosing_automation.pid_morbidostat", "Kp")
        Ki = config.getfloat("dosing_automation.pid_morbidostat", "Ki")
        Kd = config.getfloat("dosing_automation.pid_morbidostat", "Kd")

        self.pid = PID(
            -Kp,
            -Ki,
            -Kd,
            setpoint=self.target_growth_rate,
            output_limits=(0, 1),
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="growth_rate",
        )

        assert isinstance(self.duration, float)
        self.volume = round(self.target_growth_rate * self.VIAL_VOLUME * (self.duration / 60), 4)

    def execute(self) -> events.AutomationEvent:
        if self.latest_normalized_od <= self.min_od:
            return events.NoEvent(f"latest OD less than OD to start diluting, {self.min_od:.2f}")
        else:
            assert isinstance(self.duration, float)
            fraction_of_alt_media_to_add = self.pid.update(
                self.latest_growth_rate, dt=self.duration / 60
            )  # duration is measured in hours, not seconds (as simple_pid would want)

            # dilute more if our OD keeps creeping up - we want to stay in the linear range.
            if self.latest_normalized_od > self.max_od:
                self.logger.info(
                    f"executing larger dilution since we are above max OD, {self.max_od:.2f}AU."
                )
                volume_ml = 2.5 * self.volume
            else:
                volume_ml = self.volume

            alt_media_ml = fraction_of_alt_media_to_add * volume_ml
            media_ml = (1 - fraction_of_alt_media_to_add) * volume_ml

            # inaccuracies if we dose too little, so don't bother.
            minimum_dosing_volume_ml = config.getfloat(
                "dosing_automation.pid_morbidostat", "minimum_dosing_volume_ml", fallback=0.1
            )
            if alt_media_ml < minimum_dosing_volume_ml:
                volume_ml -= alt_media_ml
                alt_media_ml = 0.0
            if media_ml < minimum_dosing_volume_ml:
                volume_ml -= media_ml
                media_ml = 0.0

            self.execute_io_action(alt_media_ml=alt_media_ml, media_ml=media_ml, waste_ml=volume_ml)
            return events.AddAltMediaEvent(
                f"PID output={fraction_of_alt_media_to_add:.2f}, alt_media_ml={alt_media_ml:.2f}mL, media_ml={media_ml:.2f}mL",
                data={
                    "fraction_of_alt_media_to_add": fraction_of_alt_media_to_add,
                    "alt_media_ml": alt_media_ml,
                    "media_ml": media_ml,
                },
            )

    @property
    def min_od(self):
        return 0.7 * self.target_od

    @property
    def max_od(self):
        return 1.25 * self.target_od

    def set_target_growth_rate(self, value: str | float | int):
        self.target_growth_rate = float(value)
        with suppress(AttributeError):
            self.pid.set_setpoint(self.target_growth_rate)
