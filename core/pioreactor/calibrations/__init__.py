# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Literal
from typing import overload
from typing import TypeVar

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations.registry import calibration_protocols  # re-export
from pioreactor.calibrations.registry import CalibrationProtocol  # re-export
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env


if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations"

Device = TypeVar("Device", bound=str)


@overload
def load_active_calibration(device: pt.ODCalibrationDevices) -> structs.ODCalibration | None:
    pass


@overload
def load_active_calibration(
    device: pt.PumpCalibrationDevices,
) -> structs.SimplePeristalticPumpCalibration | None:
    pass


@overload
def load_active_calibration(device: Literal["stirring"]) -> structs.SimpleStirringCalibration | None:
    pass


def load_active_calibration(device: Device) -> structs.AnyCalibration | None:
    with local_persistent_storage("active_calibrations") as c:
        active_cal_name = c.get(device)

    if active_cal_name is None:
        return None

    return load_calibration(device, active_cal_name)


def load_calibration(device: Device, calibration_name: str) -> structs.AnyCalibration:
    target_file = CALIBRATION_PATH / device / f"{calibration_name}.yaml"

    if not target_file.exists():
        raise FileNotFoundError(
            f"Calibration {calibration_name} was not found in {CALIBRATION_PATH / device}"
        )
    elif target_file.stat().st_size == 0:
        raise FileNotFoundError(f"Calibration {calibration_name} is empty")

    try:
        data = yaml_decode(target_file.read_bytes(), type=structs.subclass_union(structs.CalibrationBase))
        return data
    except ValidationError as e:
        raise ValidationError(f"Error reading {target_file.stem}: {e}")


def list_of_calibrations_by_device(device: Device) -> list[str]:
    device_dir = CALIBRATION_PATH / device
    if not device_dir.exists():
        return []
    return [file.stem for file in device_dir.glob("*.yaml")]


def list_devices() -> list[str]:
    calibration_dir = CALIBRATION_PATH
    if not calibration_dir.exists():
        return []

    return [f.name for f in calibration_dir.iterdir() if f.is_dir()]


# Import protocols so they register with calibration_protocols.
from pioreactor.calibrations.protocols.od_reference_standard import (
    ODReferenceStandardProtocol,
)  # noqa: F401,E402
from pioreactor.calibrations.protocols.od_standards import StandardsODProtocol  # noqa: F401,E402
from pioreactor.calibrations.protocols.pump_duration_based import DurationBasedPumpProtocol  # noqa: F401,E402
from pioreactor.calibrations.protocols.stirring_dc_based import DCBasedStirringProtocol  # noqa: F401,E402
