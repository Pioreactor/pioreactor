# -*- coding: utf-8 -*-
"""
These define structs for MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

from typing import Literal

from msgspec import Struct

from pioreactor import types as pt


class Automation(Struct):
    """
    Used to change an automation over MQTT.
    """

    automation_name: str
    automation_type: Literal["temperature", "dosing", "led"]
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


class AutomationSettings(Struct):
    pioreactor_unit: str
    experiment: str
    started_at: str
    ended_at: str
    automation_name: str
    settings: str


class LEDEvent(Struct):
    channel: pt.LedChannel
    intensity: float
    source_of_event: str
    timestamp: str


class DosingEvent(Struct):
    """output of a pump action"""

    volume_change: float
    event: str
    source_of_event: str
    timestamp: str


class MeasuredRPM(Struct):
    measured_rpm: float
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
    od_raw: dict[str, ODReading]  # pt.PDChannel


class Temperature(Struct):
    timestamp: str
    temperature: float


class PumpCalibration(Struct):

    duration_: float
    hz: float
    dc: float
    bias_: float
    timestamp: str
