# -*- coding: utf-8 -*-
"""
These define structs for MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

from msgspec import Struct

import pioreactor.types as pt


class Automation(Struct):
    """
    Used to change an automation over MQTT.
    """

    automation_name: str
    automation_type: str = "unknown"
    args: dict = {}

    def __str__(self) -> str:
        s = f"{self.automation_name}("
        for k, v in self.args.items():
            s += f"{k}={v}, "

        s = s.rstrip(", ")
        s += ")"
        return s

    def __repr__(self) -> str:
        return str(self)


class DosingEvent(Struct):
    volume_change: float
    event: str
    source_of_event: str
    timestamp: str


class GrowthRate(Struct):
    growth_rate: float
    timestamp: str


class ODFiltered(Struct):
    od_filtered: float
    timestamp: str


class ODReading(Struct):
    timestamp: str
    angle: str
    voltage: float


class ODReadings(Struct):
    timestamp: str
    od_raw: dict[pt.PdChannel, ODReading]


class Temperature(Struct):
    timestamp: str
    temperature: float
