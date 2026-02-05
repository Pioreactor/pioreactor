# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env


ESTIMATOR_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "estimators"

Device = TypeVar("Device", bound=str)


def _estimator_path_for(device: str, name: str) -> Path:
    return ESTIMATOR_PATH / device / f"{name}.yaml"


def load_active_estimator(device: Device) -> structs.AnyEstimator | None:
    with local_persistent_storage("active_estimators") as storage:
        active_name = storage.get(device)

    if active_name is None:
        return None
    return load_estimator(device, active_name)


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
    device_dir = ESTIMATOR_PATH / device
    if not device_dir.is_dir():
        return []
    return [file.stem for file in device_dir.glob("*.yaml")]


def list_estimator_devices() -> list[str]:
    if not ESTIMATOR_PATH.is_dir():
        return []
    return [path.name for path in ESTIMATOR_PATH.iterdir() if path.is_dir()]
