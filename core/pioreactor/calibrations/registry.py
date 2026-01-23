# -*- coding: utf-8 -*-
from collections import defaultdict
from typing import Any
from typing import ClassVar
from typing import Generic
from typing import TypeVar

from pioreactor import structs

Device = TypeVar("Device", bound=str)
ProtocolName = str


class CalibrationProtocol(Generic[Device]):
    protocol_name: ClassVar[ProtocolName]
    target_device: ClassVar[str | list[Device]]
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    requirements: ClassVar[tuple[str, ...]] = ()
    step_registry: ClassVar[dict[str, type[Any]]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def run(self, target_device: Device) -> structs.CalibrationBase | list[structs.CalibrationBase]:
        raise NotImplementedError("Subclasses must implement this method.")


def get_calibration_protocols() -> dict[str, dict[ProtocolName, type["CalibrationProtocol[Any]"]]]:
    protocols: dict[str, dict[ProtocolName, type["CalibrationProtocol[Any]"]]] = defaultdict(dict)
    for protocol in list(CalibrationProtocol.__subclasses__()):
        target_device = protocol.target_device  # type: ignore
        protocol_name = protocol.protocol_name

        if isinstance(target_device, str):
            protocols[target_device][protocol_name] = protocol
        elif isinstance(target_device, list):
            for device in target_device:
                protocols[device][protocol_name] = protocol
        else:
            raise ValueError("target_device must be a string or a list of strings")

    return protocols


def get_protocol(target_device: str, protocol_name: ProtocolName) -> type[CalibrationProtocol[Any]]:
    device_protocols = get_calibration_protocols().get(target_device, {})
    if protocol_name in device_protocols:
        return device_protocols[protocol_name]
    raise KeyError(f"Unknown protocol '{protocol_name}' for target device '{target_device}'.")


def get_protocol_for_session(session) -> type[CalibrationProtocol[Any]]:
    return get_protocol(session.target_device, session.protocol_name)
