# -*- coding: utf-8 -*-
"""Acquisition boundary: devices return observations; the OD job publishes them.

External devices return one timestamped value, published on channel 1 at 0 degrees.
Optical-reference correction is device-owned; experiment baseline normalization
is still owned by Pioreactor's growth model. It must not be applied here.
"""
import math
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from msgspec import Struct
from pioreactor import exc
from pioreactor.hardware import ODHardwareConfig
from pioreactor.logging import CustomLogger


class ODDeviceReading(Struct):
    timestamp: datetime
    value: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("OD timestamps must include a timezone.")
        if not math.isfinite(self.value):
            raise ValueError("OD device returned an invalid observation.")


class ODDevice(Protocol):
    source: str
    signal_unit: str

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self) -> ODDeviceReading | None: ...
    def close(self) -> None: ...


type DeviceFactory = Callable[[ODHardwareConfig, CustomLogger], ODDevice]
_factories: dict[str, DeviceFactory] = {}


def register_od_device(name: str, factory: DeviceFactory) -> None:
    if name == "photodiodes":
        raise ValueError("The photodiode implementation is built in.")
    _factories[name] = factory


def create_od_device(config: ODHardwareConfig, logger: CustomLogger) -> ODDevice:
    if config.driver not in _factories:
        from pioreactor.plugin_management import get_plugins

        get_plugins()
    try:
        factory = _factories[config.driver]
    except KeyError:
        raise exc.HardwareNotFoundError(
            f"OD driver {config.driver!r} is not installed. Install its plugin or correct od.yaml."
        ) from None
    return factory(config, logger)
