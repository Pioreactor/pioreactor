# -*- coding: utf-8 -*-
"""
These define structs for internal data structures including MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union

from msgspec import Meta
from msgspec import Struct

from pioreactor import types as pt


T = TypeVar("T")


def subclass_union(cls: Type[T]) -> Type[T]:
    """Returns a Union of all subclasses of `cls` (excluding `cls` itself)"""
    classes = set()

    def _add(cls):
        for c in cls.__subclasses__():
            _add(c)
        classes.add(cls)

    for c in cls.__subclasses__():
        _add(c)
    return Union[tuple(classes)]  # type: ignore


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
        s += ", ".join(f"{k}={v}" for k, v in self.args.items())
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


AnyAutomation = Union[LEDAutomation, TemperatureAutomation, DosingAutomation]


class AutomationSettings(Struct):
    """
    Metadata produced when settings in an automation job change
    """

    pioreactor_unit: str
    experiment: str
    started_at: Annotated[datetime, Meta(tz=True)]
    ended_at: Annotated[datetime, Meta(tz=True)]
    automation_name: str
    settings: bytes


class AutomationEvent(Struct, tag=True, tag_field="event_name"):  # type: ignore
    """
    Automations can return an AutomationEvent from their `execute` method, and it
    will get published to MQTT under /latest_event
    """

    message: Optional[str] = None
    data: Optional[dict] = None

    def __str__(self) -> str:
        if self.message:
            return f"{self.human_readable_name()}: {self.message}"
        else:
            return self.human_readable_name()

    def human_readable_name(self) -> str:
        name = type(self).__name__
        return name


class LEDChangeEvent(Struct):
    """
    Produced when an LED changes value
    """

    channel: pt.LedChannel
    intensity: Annotated[float, Meta(ge=0, le=100)]
    source_of_event: str
    timestamp: Annotated[datetime, Meta(tz=True)]


class LEDsIntensity(Struct):
    A: Annotated[float, Meta(ge=0, le=100)] = 0.0
    B: Annotated[float, Meta(ge=0, le=100)] = 0.0
    C: Annotated[float, Meta(ge=0, le=100)] = 0.0
    D: Annotated[float, Meta(ge=0, le=100)] = 0.0


class DosingEvent(Struct):
    """
    Output of a pump action
    """

    volume_change: Annotated[float, Meta(ge=0)]
    event: str
    source_of_event: Optional[str]
    timestamp: Annotated[datetime, Meta(tz=True)]


class MeasuredRPM(Struct):
    measured_rpm: Annotated[float, Meta(ge=0)]
    timestamp: Annotated[datetime, Meta(tz=True)]


class GrowthRate(Struct):
    growth_rate: float
    timestamp: Annotated[datetime, Meta(tz=True)]


class ODFiltered(Struct):
    od_filtered: Annotated[float, Meta(ge=0)]
    timestamp: Annotated[datetime, Meta(tz=True)]


class ODReading(Struct):
    timestamp: Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: Annotated[float, Meta(ge=0)]
    channel: pt.PdChannel


class ODReadings(Struct):
    timestamp: Annotated[datetime, Meta(tz=True)]
    ods: dict[pt.PdChannel, ODReading]


class Temperature(Struct):
    timestamp: Annotated[datetime, Meta(tz=True)]
    temperature: float


class Calibration(Struct, tag=True, tag_field="type"):  # type: ignore
    timestamp: Annotated[datetime, Meta(tz=True)]


class PumpCalibration(Calibration):
    timestamp: Annotated[datetime, Meta(tz=True)]
    name: str
    pump: str
    hz: Annotated[float, Meta(ge=0)]
    dc: Annotated[float, Meta(ge=0)]
    duration_: float
    bias_: float
    voltage: float
    volumes: Optional[list[float]] = None
    durations: Optional[list[float]] = None


class MediaPumpCalibration(PumpCalibration, tag="media_pump"):  # type: ignore
    pass


class AltMediaPumpCalibration(PumpCalibration, tag="alt_media_pump"):  # type: ignore
    pass


class WastePumpCalibration(PumpCalibration, tag="waste_pump"):  # type: ignore
    pass


AnyPumpCalibration = Union[
    PumpCalibration, MediaPumpCalibration, AltMediaPumpCalibration, WastePumpCalibration
]


class ODCalibration(Calibration):
    timestamp: Annotated[datetime, Meta(tz=True)]
    name: str
    angle: pt.PdAngle
    maximum_od600: float
    minimum_od600: float
    minimum_voltage: float
    maximum_voltage: float
    curve_type: str
    curve_data_: list[float]
    voltages: list[float]
    inferred_od600s: list[float]
    ir_led_intensity: float
    pd_channel: pt.PdChannel


class OD45Calibration(ODCalibration, tag="od_45"):  # type: ignore
    pass


class OD90Calibration(ODCalibration, tag="od_90"):  # type: ignore
    pass


class OD135Calibration(ODCalibration, tag="od_135"):  # type: ignore
    pass


class OD180Calibration(ODCalibration, tag="od_180"):  # type: ignore
    pass


AnyODCalibration = Union[OD90Calibration, OD45Calibration, OD180Calibration, OD135Calibration]


class Log(Struct):
    message: str
    level: str
    task: str
    source: str
    timestamp: Annotated[datetime, Meta(tz=True)]


class KalmanFilterOutput(Struct):
    state: Annotated[list[float], Meta(max_length=3)]
    covariance_matrix: list[list[float]]
    timestamp: Annotated[datetime, Meta(tz=True)]
