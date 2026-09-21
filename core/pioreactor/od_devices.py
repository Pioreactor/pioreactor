# -*- coding: utf-8 -*-
"""Acquisition boundary: devices return observations; the OD job publishes them.

External devices return one timestamped value, published on logical channel 1
with device-declared geometry.
Optical-reference correction is device-owned; experiment baseline normalization
is still owned by Pioreactor's growth model. It must not be applied here.
"""
from collections.abc import Callable
from typing import Any
from typing import Protocol

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.hardware import ODHardwareConfig
from pioreactor.logging import CustomLogger


class ExternalODDevice(Protocol):
    source: str
    angle: pt.ObservationAngle

    def start(self) -> None:
        """Begin acquisition or resume after pause()."""

    def pause(self) -> None:
        """Suspend acquisition while retaining resources for start()."""

    def read(self) -> structs.ODDeviceReading | None:
        """Read the device"""

    def close(self) -> None:
        """End acquisition and release resources, whether running or paused."""


type DeviceFactory = Callable[[dict[str, Any], CustomLogger], ExternalODDevice]
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
    return factory(config.options, logger)
