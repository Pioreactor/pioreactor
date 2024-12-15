# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Callable
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode
from pioreactor import structs
from pioreactor.whoami import is_testing_env
from pioreactor.utils import local_persistant_storage

if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(".pioreactor/storage/calibrations/")

# Lookup table for different calibration assistants
calibration_assistants = {}


class CalibrationAssistant:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        calibration_assistants[cls.target_calibration_type] = cls

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method.")


class ODAssistant(CalibrationAssistant):
    target_calibration_type = "od"
    calibration_struct = structs.ODCalibration

    def __init__(self):
        pass

    def run(self) -> structs.ODCalibration:
        from pioreactor.calibrations.od_calibration import run_od_calibration

        return run_od_calibration(od_channel=od_channel)

class PumpAssistant(CalibrationAssistant):
    target_calibration_type = "pump"
    calibration_struct = structs.PumpCalibration

    def __init__(self):
        pass

    def run(self) -> structs.PumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration()


class StirringAssistant(CalibrationAssistant):
    target_calibration_type = "stirring"
    calibration_struct = structs.StirringCalibration

    def __init__(self):
        pass

    def run(self, min_dc: str | None = None, max_dc: str | None = None) -> structs.StirringCalibration:
        from pioreactor.calibrations.stirring_calibration import run_stirring_calibration

        return run_stirring_calibration(
            min_dc=float(min_dc) if min_dc is not None else None, max_dc=float(max_dc) if max_dc else None
        )


def load_active_calibration(cal_type: str, cal_subtype: str | None=None) -> None | structs.AnyCalibration:

    with local_persistant_storage("active_calibrations") as c:
        active_cal_name = c.get((cal_type, cal_subtype))

    if active_cal_name is None:
        return None

    return load_calibration(cal_type, active_cal_name)

def load_calibration(cal_type: str, calibration_name: str) -> structs.AnyCalibration:

    target_file = CALIBRATION_PATH / cal_type / f"{calibration_name}.yaml"

    if not target_file.exists():
        raise FileNotFoundError(f"Calibration {calibration_name} was not found in {CALIBRATION_PATH / cal_type}")

    assistant = calibration_assistants[cal_type]

    try:
        data = yaml_decode(target_file.read_bytes(), type=assistant.calibration_struct)
        return data
    except ValidationError as e:
        raise ValidationError(f"Error reading {target_file.stem()}: {e}")

