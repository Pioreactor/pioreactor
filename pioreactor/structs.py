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


class JsonReprStuct(Struct):
    def __str__(self):
        return encode(self).decode()


class AutomationSettings(JsonReprStuct):
    """
    Metadata produced when settings in an automation job change
    """

    pioreactor_unit: str
    experiment: str
    started_at: t.Annotated[datetime, Meta(tz=True)]
    ended_at: t.Optional[t.Annotated[datetime, Meta(tz=True)]]
    automation_name: str
    settings: bytes


class AutomationEvent(JsonReprStuct, tag=True, tag_field="event_name"):  # type: ignore
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


class LEDChangeEvent(JsonReprStuct):
    """
    Produced when an LED changes value
    """

    channel: pt.LedChannel
    intensity: pt.LedIntensityValue
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class DosingEvent(JsonReprStuct):
    """
    Output of a pump action
    """

    volume_change: t.Annotated[float, Meta(ge=0)]
    event: str
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class MeasuredRPM(JsonReprStuct):
    measured_rpm: t.Annotated[float, Meta(ge=0)]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class GrowthRate(JsonReprStuct):
    growth_rate: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODFiltered(JsonReprStuct):
    od_filtered: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODReading(JsonReprStuct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: pt.OD
    channel: pt.PdChannel


class ODReadings(JsonReprStuct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    ods: dict[pt.PdChannel, ODReading]


class Temperature(JsonReprStuct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    temperature: float


class Voltage(JsonReprStuct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    voltage: pt.Voltage


class Calibration(JsonReprStuct, tag=True, tag_field="type"):
    created_at: t.Annotated[datetime, Meta(tz=True)]
    pioreactor_unit: str
    name: str

    @property
    def type(self) -> str:
        return self.__struct_config__.tag  # type: ignore


class PumpCalibration(Calibration):
    pump: str
    hz: t.Annotated[float, Meta(ge=0)]
    dc: t.Annotated[float, Meta(ge=0)]
    duration_: t.Annotated[float, Meta(ge=0)]
    bias_: float
    voltage: float
    volumes: t.Optional[list[float]] = None
    durations: t.Optional[list[float]] = None

    def ml_to_duration(self, ml: pt.mL) -> pt.Seconds:
        duration_ = self.duration_
        bias_ = self.bias_
        return t.cast(pt.Seconds, (ml - bias_) / duration_)

    def duration_to_ml(self, duration: pt.Seconds) -> pt.mL:
        duration_ = self.duration_
        bias_ = self.bias_
        return t.cast(pt.mL, duration * duration_ + bias_)


class MediaPumpCalibration(PumpCalibration, tag="media_pump"):
    pass


class AltMediaPumpCalibration(PumpCalibration, tag="alt_media_pump"):
    pass


class WastePumpCalibration(PumpCalibration, tag="waste_pump"):
    pass


AnyPumpCalibration = t.Union[
    PumpCalibration, MediaPumpCalibration, AltMediaPumpCalibration, WastePumpCalibration
]


class ODCalibration(Calibration):
    angle: pt.PdAngle
    maximum_od600: pt.OD
    minimum_od600: pt.OD
    minimum_voltage: pt.Voltage
    maximum_voltage: pt.Voltage
    curve_type: str
    curve_data_: list[float]
    voltages: list[pt.Voltage]
    od600s: list[pt.OD]
    ir_led_intensity: float
    pd_channel: pt.PdChannel


class OD45Calibration(ODCalibration, tag="od_45"):
    pass


class OD90Calibration(ODCalibration, tag="od_90"):
    pass


class OD135Calibration(ODCalibration, tag="od_135"):
    pass


class OD180Calibration(ODCalibration, tag="od_180"):
    pass


AnyODCalibration = t.Union[OD90Calibration, OD45Calibration, OD180Calibration, OD135Calibration]


class Log(JsonReprStuct):
    message: str
    level: str
    task: str
    source: str
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class KalmanFilterOutput(JsonReprStuct):
    state: t.Annotated[list[float], Meta(max_length=3)]
    covariance_matrix: list[list[float]]
    timestamp: t.Annotated[datetime, Meta(tz=True)]
