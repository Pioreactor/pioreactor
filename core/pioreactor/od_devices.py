# -*- coding: utf-8 -*-
"""Acquisition boundary: devices return observations; the OD job publishes them.

External devices return one timestamped value, published on channel 1 at 0 degrees.
Optical-reference correction is device-owned; experiment baseline normalization
is still owned by Pioreactor's growth model. It must not be applied here.
"""
from collections.abc import Callable
from typing import Protocol

from pioreactor import exc
from pioreactor import structs
from pioreactor.hardware import ODHardwareConfig
from pioreactor.logging import CustomLogger


class ExternalODDevice(Protocol):
    source: str
    signal_unit: str

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self) -> structs.ODDeviceReading | None: ...
    def close(self) -> None: ...


type DeviceFactory = Callable[[ODHardwareConfig, CustomLogger], ExternalODDevice]
_factories: dict[str, DeviceFactory] = {}


def register_od_device(name: str, factory: DeviceFactory) -> None:
    if name == "photodiodes":
        raise ValueError("The photodiode implementation is built in.")
    _factories[name] = factory


def create_od_device(config: ODHardwareConfig, logger: CustomLogger) -> ExternalODDevice:
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
