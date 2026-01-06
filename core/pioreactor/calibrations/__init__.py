# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Generic
from typing import Literal
from typing import overload
from typing import TypeVar

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env


if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations"

# Lookup table for different calibration protocols
Device = TypeVar("Device", bound=str)
ProtocolName = str

calibration_protocols: dict[str, dict[ProtocolName, type[CalibrationProtocol[Any]]]] = defaultdict(dict)


class CalibrationProtocol(Generic[Device]):
    protocol_name: ClassVar[ProtocolName]
    target_device: ClassVar[str | list[str]]
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if isinstance(cls.target_device, str):
            calibration_protocols[cls.target_device][cls.protocol_name] = cls
        elif isinstance(cls.target_device, list):
            for device in cls.target_device:
                calibration_protocols[device][cls.protocol_name] = cls
        else:
            raise ValueError("target_device must be a string or a list of strings")

    def run(self, target_device: Device) -> structs.CalibrationBase | list[structs.CalibrationBase]:
        raise NotImplementedError("Subclasses must implement this method.")


class SingleVialODProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = pt.OD_DEVICES
    protocol_name = "single_vial"
    description = "Calibrate OD using a single vial"

    def run(self, target_device: pt.ODCalibrationDevices, **kwargs) -> structs.OD600Calibration:
        from pioreactor.calibrations.od_calibration_single_vial import run_od_calibration

        return run_od_calibration(target_device)


class StandardsODProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = pt.OD_DEVICES
    protocol_name = "standards"
    description = "Calibrate OD using standards. Requires multiple vials"

    def run(  # type: ignore
        self, target_device: pt.ODCalibrationDevices, *args, **kwargs
    ) -> structs.OD600Calibration | list[structs.OD600Calibration]:
        from pioreactor.calibrations.od_calibration_using_standards import run_od_calibration

        return run_od_calibration(target_device)


class ODReferenceStandardProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = pt.OD_DEVICES
    protocol_name = "od_reference_standard"
    description = "Calibrate OD using the Pioreactor Optical Reference Standard."

    def run(  # type: ignore
        self, target_device: pt.ODCalibrationDevices, *args, **kwargs
    ) -> list[structs.ODCalibration]:
        from pioreactor.calibrations.od_calibration_using_OD_reference_standard import run_od_calibration

        return run_od_calibration(target_device)


class DurationBasedPumpProtocol(CalibrationProtocol[pt.PumpCalibrationDevices]):
    target_device = pt.PUMP_DEVICES
    protocol_name = "duration_based"

    def run(
        self, target_device: pt.PumpCalibrationDevices, **kwargs
    ) -> structs.SimplePeristalticPumpCalibration:
        from pioreactor.calibrations.pump_calibration import run_pump_calibration

        return run_pump_calibration(target_device)


class DCBasedStirringProtocol(CalibrationProtocol[Literal["stirring"]]):
    target_device = "stirring"
    protocol_name = "dc_based"

    def run(
        self, target_device: Literal["stirring"], min_dc: str | None = None, max_dc: str | None = None
    ) -> structs.SimpleStirringCalibration:
        from pioreactor.calibrations.stirring_calibration import run_stirring_calibration

        return run_stirring_calibration(
            min_dc=float(min_dc) if min_dc is not None else None, max_dc=float(max_dc) if max_dc else None
        )


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
