# -*- coding: utf-8 -*-
"""Acquisition boundary: devices return signals; the OD job calibrates and publishes them.

Every OD device, the built-in photodiodes included, implements `ODDevice`. A device
declares its outputs as `ODSignal`s on logical channels "1".."4" and returns their raw
values. Channel 1 is the device's primary biomass signal.

The OD job owns everything after acquisition: applying Pioreactor calibrations,
publishing `od*`, `raw_od*` and `ods`, and the job lifecycle. Device-owned work is
limited to producing its signals, including any optical-reference correction.
Experiment baseline normalization belongs to Pioreactor's growth model and must not
be applied by a device.

A unit selects exactly one driver in od.yaml, so two OD devices never run together.
"""
from collections.abc import Callable
from collections.abc import Mapping
from typing import Any
from typing import Protocol

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.hardware import ODHardwareConfig
from pioreactor.logging import CustomLogger

PHOTODIODE_DRIVER = "photodiodes"


class ODDevice(Protocol):
    @property
    def outputs(self) -> Mapping[pt.PdChannel, structs.ODSignal]:
        """Each published channel's signal. Valid after the first start().

        `name` and `angle` stay fixed while the device is open; `scale` may change
        between reads, for example when an LED intensity is changed.
        """

    def start(self) -> None:
        """Begin acquisition or resume after pause()."""

    def pause(self) -> None:
        """Suspend acquisition while retaining resources for start()."""

    def read(self) -> structs.ODDeviceReadings | None:
        """The latest acquisition with a value for every output, or None if nothing is new."""

    def close(self) -> None:
        """End acquisition and release resources, whether running, paused or never started."""


type DeviceFactory = Callable[[dict[str, Any], CustomLogger], ODDevice]
_factories: dict[str, DeviceFactory] = {}


def register_od_device(name: str, factory: DeviceFactory) -> None:
    if name == PHOTODIODE_DRIVER:
        raise ValueError("The photodiode implementation is built in.")
    _factories[name] = factory


def od_calibration_device(driver: str, signal: str) -> str:
    """Where calibrations of one OD signal are stored.

    Photodiode signals keep their historical names (`od90`); external signals are
    namespaced by driver (`od_turbidvision_reflectance`).
    """
    if driver == PHOTODIODE_DRIVER:
        return f"od{signal}"
    return f"od_{driver}_{signal}"


def od_calibration_protocol_device(driver: str) -> str:
    """Protocol target that calibrates every uncalibrated output of an external driver."""
    return f"od_{driver}"


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
    return factory(config.options, logger)
