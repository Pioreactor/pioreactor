# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode
from pioreactor import structs
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import is_testing_env


ESTIMATOR_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "estimators"

Device = TypeVar("Device", bound=str)


def _estimator_path_for(device: str, name: str) -> Path:
    return ESTIMATOR_PATH / device / f"{name}.yaml"


def load_active_estimator(device: Device) -> structs.ODFusionEstimator | None:
    with local_persistent_storage("active_estimators") as storage:
        active_name = storage.get(device)

    if active_name is None:
        return None
    return load_estimator(device, active_name)


def load_estimator(device: Device, estimator_name: str) -> structs.ODFusionEstimator:
    target_file = _estimator_path_for(device, estimator_name)
    if not target_file.exists():
        raise FileNotFoundError(f"Estimator {estimator_name} was not found in {ESTIMATOR_PATH / device}")
    if target_file.stat().st_size == 0:
        raise FileNotFoundError(f"Estimator {estimator_name} is empty")

    try:
        return yaml_decode(target_file.read_bytes(), type=structs.ODFusionEstimator)
    except ValidationError as exc:
        raise ValidationError(f"Error reading {target_file.stem}: {exc}") from exc


def save_estimator(device: Device, estimator: structs.ODFusionEstimator) -> str:
    out_file = _estimator_path_for(device, estimator.estimator_name)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("wb") as handle:
        handle.write(yaml_encode(estimator))
    return str(out_file)


def set_active_estimator(device: Device, estimator_name: str) -> None:
    with local_persistent_storage("active_estimators") as storage:
        storage[device] = estimator_name


def remove_active_estimator(device: Device) -> None:
    with local_persistent_storage("active_estimators") as storage:
        if storage.get(device) is not None:
            storage.pop(device, None)


def list_of_estimators_by_device(device: Device) -> list[str]:
    device_dir = ESTIMATOR_PATH / device
    if not device_dir.exists():
        return []
    return [file.stem for file in device_dir.glob("*.yaml")]


def list_estimator_devices() -> list[str]:
    if not ESTIMATOR_PATH.exists():
        return []
    return [path.name for path in ESTIMATOR_PATH.iterdir() if path.is_dir()]
