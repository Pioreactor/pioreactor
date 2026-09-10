"""Small plugin boundary for independently acquiring OD sensors.

Drivers own acquisition and return a new optical-power-normalized observation,
or None when there is no new sample. They do not publish MQTT or normalize by
the experiment's initial value. Pioreactor owns those responsibilities.
"""

from collections.abc import Callable
from typing import Protocol

from pioreactor import exc
from pioreactor.hardware import ODHardwareConfig
from pioreactor.logging import CustomLogger


class ODSource(Protocol):
    signal_unit: str

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self) -> float | None: ...
    def close(self) -> None: ...


type SourceFactory = Callable[[ODHardwareConfig, CustomLogger], ODSource]

_factories: dict[str, SourceFactory] = {}


def register_od_source(name: str, factory: SourceFactory) -> None:
    if name == "photodiodes":
        raise ValueError("The photodiode implementation is built in.")
    _factories[name] = factory


def create_od_source(config: ODHardwareConfig, logger: CustomLogger) -> ODSource:
    if config.driver not in _factories:
        # Python callers (including Huey) need the same registration as pio run.
        from pioreactor.plugin_management import get_plugins

        get_plugins()
    try:
        factory = _factories[config.driver]
    except KeyError:
        raise exc.HardwareNotFoundError(
            f"OD driver {config.driver!r} is not installed. Install its plugin or correct od.yaml."
        ) from None
    return factory(config, logger)
