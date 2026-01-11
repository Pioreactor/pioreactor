# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from typing import Any
from typing import ClassVar
from typing import Generic
from typing import TypeVar

from pioreactor import structs

Device = TypeVar("Device", bound=str)
ProtocolName = str

# Registry of device -> protocol name -> protocol class (populated via CalibrationProtocol subclasses).
calibration_protocols: dict[str, dict[ProtocolName, type["CalibrationProtocol[Any]"]]] = defaultdict(dict)


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


def get_protocol(target_device: str, protocol_name: ProtocolName) -> type[CalibrationProtocol[Any]]:
    device_protocols = calibration_protocols.get(target_device, {})
    if protocol_name in device_protocols:
        return device_protocols[protocol_name]
    raise KeyError(f"Unknown protocol '{protocol_name}' for target device '{target_device}'.")


def get_protocol_for_session(session) -> type[CalibrationProtocol[Any]]:
    return get_protocol(session.target_device, session.protocol_name)
