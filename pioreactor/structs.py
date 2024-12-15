# -*- coding: utf-8 -*-
"""
These define structs for internal data structures including MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

import typing as t
from datetime import datetime

from msgspec import Meta
from msgspec import Struct
from msgspec.json import encode

from pioreactor import types as pt


T = t.TypeVar("T")


def subclass_union(cls: t.Type[T]) -> t.Type[T]:
    """Returns a Union of all subclasses of `cls` (excluding `cls` itself)"""
    classes = set()

    def _add(cls):
        for c in cls.__subclasses__():
            _add(c)
        classes.add(cls)

    for c in cls.__subclasses__():
        _add(c)
    return t.Union[tuple(classes)]  # type: ignore


class JSONPrintedStruct(Struct):
    def __str__(self):
        return encode(self).decode()  # this is a valid JSON str, decode() for bytes->str


class AutomationSettings(JSONPrintedStruct):
    """
    Metadata produced when settings in an automation job change
    """

    pioreactor_unit: str
    experiment: str
    started_at: t.Annotated[datetime, Meta(tz=True)]
    ended_at: t.Optional[t.Annotated[datetime, Meta(tz=True)]]
    automation_name: str
    settings: bytes


class AutomationEvent(JSONPrintedStruct, tag=True, tag_field="event_name"):  # type: ignore
    """
    Automations can return an AutomationEvent from their `execute` method, and it
    will get published to MQTT under /latest_event
    """

    message: t.Optional[str] = None
    data: t.Optional[dict] = None

    def display(self) -> str:
        if self.message:
            return f"{self.human_readable_name}: {self.message}"
        else:
            return self.human_readable_name

    @property
    def human_readable_name(self) -> str:
        name = type(self).__name__
        return name

    # @property
    # def type(self) -> str:
    #    return self.__class__.__struct_tag__  # type: ignore


class LEDChangeEvent(JSONPrintedStruct):
    """
    Produced when an LED changes value
    """

    channel: pt.LedChannel
    intensity: pt.LedIntensityValue
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class DosingEvent(JSONPrintedStruct):
    """
    Output of a pump action
    """

    volume_change: t.Annotated[float, Meta(ge=0)]
    event: str
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class MeasuredRPM(JSONPrintedStruct):
    measured_rpm: t.Annotated[float, Meta(ge=0)]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class GrowthRate(JSONPrintedStruct):
    growth_rate: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODFiltered(JSONPrintedStruct):
    od_filtered: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODReading(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: pt.OD
    channel: pt.PdChannel


class ODReadings(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    ods: dict[pt.PdChannel, ODReading]


class Temperature(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    temperature: float


class Voltage(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    voltage: pt.Voltage


def to_calibration_tag(s: str) -> str:
    return s.lower().removesuffix("calibration")


class CalibrationBase(Struct, tag_field="calibration_type", tag=to_calibration_tag, kw_only=True):
    calibration_name: str
    pioreactor_unit: str
    created_at: t.Annotated[datetime, Meta(tz=True)]
    curve_data_: list[float]
    curve_type: str  # ex: "poly"
    x: str  # ex: voltage
    y: str  # ex: od600
    recorded_data: dict[t.Literal["x", "y"], list[float]]
    calibration_subtype: str | None = None


class CalibrationBaseWithSubtype(CalibrationBase, kw_only=True):
    calibration_subtype: str  # example: waste, media or alt_media. Or 90, 135, etc.


class ODCalibration(CalibrationBaseWithSubtype, kw_only=True):
    ir_led_intensity: float


class PumpCalibration(CalibrationBaseWithSubtype, kw_only=True):
    hz: t.Annotated[float, Meta(ge=0)]
    dc: t.Annotated[float, Meta(ge=0)]
    voltage: float
    x: str = "duration"
    y: str = "volume"

    def ml_to_duration(self, ml: pt.mL) -> pt.Seconds:
        duration_ = self.duration_
        bias_ = self.bias_
        return t.cast(pt.Seconds, (ml - bias_) / duration_)

    def duration_to_ml(self, duration: pt.Seconds) -> pt.mL:
        duration_ = self.duration_
        bias_ = self.bias_
        return t.cast(pt.mL, duration * duration_ + bias_)


class StirringCalibration(CalibrationBase, kw_only=True):
    pwm_hz: t.Annotated[float, Meta(ge=0)]
    voltage: float
    x: str = "DC %"
    y: str = "RPM"


class Log(JSONPrintedStruct):
    message: str
    level: str
    task: str
    source: str
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class KalmanFilterOutput(JSONPrintedStruct):
    state: t.Annotated[list[float], Meta(max_length=3)]
    covariance_matrix: list[list[float]]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class Dataset(JSONPrintedStruct):
    dataset_name: str  # the unique key
    description: t.Optional[str]
    display_name: str
    has_experiment: bool
    has_unit: bool
    default_order_by: t.Optional[str]
    table: t.Optional[str] = None
    query: t.Optional[str] = None
    source: str = "app"
    timestamp_columns: list[str] = []
    always_partition_by_unit: bool = False
