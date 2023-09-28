# -*- coding: utf-8 -*-
"""
These define structs for internal data structures including MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

import typing as t
from datetime import datetime

from msgspec import Meta
from msgspec import Struct

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


class Automation(Struct):
    """
    Used to change an automation over MQTT.
    """

    automation_name: str
    args: dict = {}

    def __str__(self) -> str:
        s = ""
        s += f"{self.automation_name}"
        s += "("
        for i, (k, v) in enumerate(self.args.items()):
            if k == "skip_first_run":
                v = bool(int(v))
            if i == 0:
                s += f"{k}={v}"
            else:
                s += f", {k}={v}"

        s += ")"
        return s

    def __repr__(self) -> str:
        return str(self)


class TemperatureAutomation(Automation, tag="temperature"):  # type: ignore
    ...


class DosingAutomation(Automation, tag="dosing"):  # type: ignore
    ...


class LEDAutomation(Automation, tag="led"):  # type: ignore
    ...


AnyAutomation = t.Union[LEDAutomation, TemperatureAutomation, DosingAutomation]


class AutomationSettings(Struct):
    """
    Metadata produced when settings in an automation job change
    """

    pioreactor_unit: str
    experiment: str
    started_at: t.Annotated[datetime, Meta(tz=True)]
    ended_at: t.Optional[t.Annotated[datetime, Meta(tz=True)]]
    automation_name: str
    settings: bytes


class AutomationEvent(Struct, tag=True, tag_field="event_name"):  # type: ignore
    """
    Automations can return an AutomationEvent from their `execute` method, and it
    will get published to MQTT under /latest_event
    """

    message: t.Optional[str] = None
    data: t.Optional[dict] = None

    def __str__(self) -> str:
        if self.message:
            return f"{self.human_readable_name}: {self.message}"
        else:
            return self.human_readable_name

    @property
    def human_readable_name(self) -> str:
        name = type(self).__name__
        return name

    @property
    def type(self) -> str:
        return self.__class__.__struct_tag__  # type: ignore


class LEDChangeEvent(Struct):
    """
    Produced when an LED changes value
    """

    channel: pt.LedChannel
    intensity: pt.LedIntensityValue
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class LEDsIntensity(Struct):
    A: pt.LedIntensityValue = 0.0
    B: pt.LedIntensityValue = 0.0
    C: pt.LedIntensityValue = 0.0
    D: pt.LedIntensityValue = 0.0


class DosingEvent(Struct):
    """
    Output of a pump action
    """

    volume_change: t.Annotated[float, Meta(ge=0)]
    event: str
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class MeasuredRPM(Struct):
    measured_rpm: t.Annotated[float, Meta(ge=0)]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class GrowthRate(Struct):
    growth_rate: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODFiltered(Struct):
    od_filtered: t.Annotated[float, Meta(ge=0)]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODReading(Struct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: t.Annotated[float, Meta(ge=0)]
    channel: pt.PdChannel


class ODReadings(Struct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    ods: dict[pt.PdChannel, ODReading]


class Temperature(Struct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    temperature: float


class Voltage(Struct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    voltage: pt.Voltage


class Calibration(Struct, tag=True, tag_field="type"):
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


class Log(Struct):
    message: str
    level: str
    task: str
    source: str
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class KalmanFilterOutput(Struct):
    state: t.Annotated[list[float], Meta(max_length=3)]
    covariance_matrix: list[list[float]]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ExperimentMetadata(Struct):
    experiment: str
