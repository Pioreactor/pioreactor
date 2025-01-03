# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Literal
from typing import overload

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor import structs
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env

if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(".pioreactor/storage/calibrations/")

# Lookup table for different calibration assistants
calibration_assistants = {}


class CalibrationAssistant:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        calibration_assistants[cls.target_device] = cls

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method.")


class ODAssistant(CalibrationAssistant):
    target_device = "od"
    calibration_struct = structs.ODCalibration

    def run(self) -> structs.ODCalibration:
        from pioreactor.calibrations.od_calibration import run_od_calibration

        return run_od_calibration()


class MediaPumpAssistant(CalibrationAssistant):
    target_device = "media_pump"
    calibration_struct = structs.SimplePeristalticPumpCalibration

    def run(self) -> structs.SimplePeristalticPumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration()


class AltMediaPumpAssistant(CalibrationAssistant):
    target_device = "alt_media_pump"
    calibration_struct = structs.SimplePeristalticPumpCalibration

    def run(self) -> structs.SimplePeristalticPumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration()


class WastePumpAssistant(CalibrationAssistant):
    target_device = "waste_pump"
    calibration_struct = structs.SimplePeristalticPumpCalibration

    def run(self) -> structs.SimplePeristalticPumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration()


class StirringAssistant(CalibrationAssistant):
    target_device = "stirring"
    calibration_struct = structs.SimpleStirringCalibration

    def run(self, min_dc: str | None = None, max_dc: str | None = None) -> structs.SimpleStirringCalibration:
        from pioreactor.calibrations.stirring_calibration import run_stirring_calibration

        return run_stirring_calibration(
            min_dc=float(min_dc) if min_dc is not None else None, max_dc=float(max_dc) if max_dc else None
        )


@overload
def load_active_calibration(device: Literal["od"]) -> structs.ODCalibration:
    pass


@overload
def load_active_calibration(
    device: Literal["media_pump", "waste_pump", "alt_media_pump"]
) -> structs.SimplePeristalticPumpCalibration:
    pass


@overload
def load_active_calibration(device: Literal["stirring"]) -> structs.SimpleStirringCalibration:
    pass


def load_active_calibration(device: str) -> None | structs.AnyCalibration:
    with local_persistent_storage("active_calibrations") as c:
        active_cal_name = c.get(device)

    if active_cal_name is None:
        return None

    return load_calibration(device, active_cal_name)


def load_calibration(device: str, calibration_name: str) -> structs.AnyCalibration:
    target_file = CALIBRATION_PATH / device / f"{calibration_name}.yaml"

    if not target_file.exists():
        raise FileNotFoundError(
            f"Calibration {calibration_name} was not found in {CALIBRATION_PATH / device}"
        )

    assistant = calibration_assistants[device]

    try:
        data = yaml_decode(target_file.read_bytes(), type=assistant.calibration_struct)
        return data
    except ValidationError as e:
        raise ValidationError(f"Error reading {target_file.stem}: {e}")
