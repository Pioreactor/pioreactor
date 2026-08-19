# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import cast
from typing import overload
from typing import TypeVar

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.structs import artifact_path_component
from pioreactor.utils import local_persistent_storage


ESTIMATOR_PATH = get_dot_pioreactor_path() / "storage" / "estimators"

Device = TypeVar("Device", bound=str)


def _estimator_path_for(device: str, name: str) -> Path:
    device = artifact_path_component(device, "device")
    name = artifact_path_component(name, "estimator_name")
    return ESTIMATOR_PATH / device / f"{name}.yaml"


@overload
def load_active_estimator(device: pt.ODFusedCalibrationDevice) -> structs.ODFusionEstimator | None:
    pass


@overload
def load_active_estimator(device: Device) -> structs.AnyEstimator | None:
    pass


def load_active_estimator(device: Device) -> structs.AnyEstimator | None:
    with local_persistent_storage("active_estimators") as storage:
        active_name = cast(str | None, storage.get(device))

    if active_name is None:
        return None
    return load_estimator(device, active_name)


@overload
def load_estimator(device: pt.ODFusedCalibrationDevice, estimator_name: str) -> structs.ODFusionEstimator:
    pass


@overload
def load_estimator(device: Device, estimator_name: str) -> structs.AnyEstimator:
    pass


def load_estimator(device: Device, estimator_name: str) -> structs.AnyEstimator:
    target_file = _estimator_path_for(device, estimator_name)
    if not target_file.is_file():
        raise FileNotFoundError(f"Estimator {estimator_name} was not found in {ESTIMATOR_PATH / device}")
    if target_file.stat().st_size == 0:
        raise FileNotFoundError(f"Estimator {estimator_name} is empty")

    try:
        return yaml_decode(target_file.read_bytes(), type=structs.subclass_union(structs.EstimatorBase))
    except ValidationError as exc:
        raise ValidationError(f"Error reading {target_file.stem}: {exc}") from exc


def list_of_estimators_by_device(device: Device) -> list[str]:
    valid_device = artifact_path_component(device, "device")
    device_dir = ESTIMATOR_PATH / valid_device
    if not device_dir.is_dir():
        return []
    return [file.stem for file in device_dir.glob("*.yaml")]


def list_estimator_devices() -> list[str]:
    if not ESTIMATOR_PATH.is_dir():
        return []
    return [path.name for path in ESTIMATOR_PATH.iterdir() if path.is_dir()]
