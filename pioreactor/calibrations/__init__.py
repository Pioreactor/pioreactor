# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Literal
from typing import overload
from typing import Type

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor import structs
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env

if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(".pioreactor/storage/calibrations/")

# Lookup table for different calibration protocols
calibration_protocols: dict[tuple[str, str], Type[CalibrationProtocol]] = {}


class CalibrationProtocol:
    protocol_name: str
    target_device: str | list[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if isinstance(cls.target_device, str):
            calibration_protocols[(cls.target_device, cls.protocol_name)] = cls
        elif isinstance(cls.target_device, list):
            for device in cls.target_device:
                calibration_protocols[(device, cls.protocol_name)] = cls
        else:
            raise ValueError("target_device must be a string or a list of strings")

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method.")


class SingleVialODProtocol(CalibrationProtocol):
    target_device = "od"
    protocol_name = "single_vial"

    def run(self, *args, **kwargs) -> structs.ODCalibration:
        from pioreactor.calibrations.od_calibration import run_od_calibration

        return run_od_calibration()


class BatchVialODProtocol(CalibrationProtocol):
    target_device = "od"
    protocol_name = "batch_vial"

    def run(self, *args, **kwargs) -> structs.ODCalibration:
        raise NotImplementedError("Not implemented yet")


class DurationBasedPumpProtocol(CalibrationProtocol):
    target_device = ["media_pump", "alt_media_pump", "waste_pump"]
    protocol_name = "duration_based"

    def run(self, target_device: str, **kwargs) -> structs.SimplePeristalticPumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration(target_device)


class DCBasedStirringProtocol(CalibrationProtocol):
    target_device = "stirring"
    protocol_name = "dc_based"

    def run(
        self, target_device: str, min_dc: str | None = None, max_dc: str | None = None
    ) -> structs.SimpleStirringCalibration:
        from pioreactor.calibrations.stirring_calibration import run_stirring_calibration

        return run_stirring_calibration(
            min_dc=float(min_dc) if min_dc is not None else None, max_dc=float(max_dc) if max_dc else None
        )


@overload
def load_active_calibration(device: Literal["od"]) -> structs.ODCalibration | None:
    pass


@overload
def load_active_calibration(
    device: PumpCalibrationDevices,
) -> structs.SimplePeristalticPumpCalibration | None:
    pass


@overload
def load_active_calibration(device: Literal["stirring"]) -> structs.SimpleStirringCalibration | None:
    pass


def load_active_calibration(device: str) -> structs.AnyCalibration | None:
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

    try:
        data = yaml_decode(target_file.read_bytes(), type=structs.subclass_union(structs.CalibrationBase))
        return data
    except ValidationError as e:
        raise ValidationError(f"Error reading {target_file.stem}: {e}")


def list_of_calibrations_by_device(device: str) -> list[str]:
    device_dir = CALIBRATION_PATH / device
    if not device_dir.exists():
        return []

    return [file.stem for file in device_dir.glob("*.yaml")]


def list_devices() -> list[str]:
    calibration_dir = CALIBRATION_PATH
    if not calibration_dir.exists():
        return []

    return [f.name for f in calibration_dir.iterdir() if f.is_dir()]
