# -*- coding: utf-8 -*-
# types
from __future__ import annotations

import typing as t

from msgspec import Meta


class DosingProgram(t.Protocol):
    """
    Should return a non-negative float representing (approx) how much liquid was moved, in ml.
    """

    def __call__(self, unit: str, experiment: str, ml: float, source_of_event: str) -> float:
        # don't forget to return a float!
        ...


MQTTMessagePayload = t.Union[bytes, bytearray]


class MQTTMessage:
    payload: MQTTMessagePayload
    topic: str
    qos: t.Literal[0, 1, 2]
    retain: bool
    mid: int


PublishableSettingDataType = t.Union[str, float, int, bool]


class PublishableSetting(t.TypedDict, total=False):
    """
    In a job, the published_settings attribute is a list of dictionaries that have
    the below schema.

    datatype:
        string: a string
        float: a float
        integer: an integer
        json: this can have arbitrary data in it.
        boolean: must be 0 or 1 (this is unlike the Homie convention)
        Automation: json encoded struct.Automation

    unit (optional):
        a string representing what the unit suffix is

    settable:
        a bool representing if the attribute can be changed over MQTT

    persist (optional):
        a bool representing if the attr should be cleared when the job cleans up. Default False.

    """

    datatype: t.Literal[
        "string",
        "float",
        "integer",
        "json",
        "boolean",
        "Automation",
        "GrowthRate",
        "ODFiltered",
        "Temperature",
        "MeasuredRPM",
        "AutomationEvent",
        "Voltage",
        "KalmanFilterOutput",
    ]
    unit: str
    settable: bool
    persist: bool


JobState = t.Literal["init", "ready", "sleeping", "disconnected", "lost"]


LedChannel = t.Literal["A", "B", "C", "D"]
# these are strings! Don't make them ints, since ints suggest we can perform math on them, that's meaningless.
# str suggest symbols, which they are.
PdChannel = t.Literal["1", "2"]
PwmChannel = t.Literal["1", "2", "3", "4", "5"]

PdAngle = t.Literal["45", "90", "135", "180"]
PdAngleOrREF = t.Union[PdAngle, t.Literal["REF"]]

# hardware level stuff
AnalogValue = t.Union[int, float]
Voltage = float  # maybe should be non-negative?
OD = float  # maybe should be non-negative?

AdcChannel = t.Literal[0, 1, 2, 3]

FloatBetween0and100 = t.Annotated[float, Meta(ge=0, le=100)]
LedIntensityValue = FloatBetween0and100

# All GPIO pins below are BCM numbered
GpioPin = t.Literal[
    2,
    3,
    4,
    14,
    15,
    17,
    18,
    27,
    22,
    23,
    24,
    10,
    9,
    25,
    11,
    8,
    7,
    0,
    1,
    5,
    6,
    12,
    13,
    19,
    16,
    26,
    20,
    21,
]

mL = float
Seconds = float
