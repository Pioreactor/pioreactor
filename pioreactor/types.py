# -*- coding: utf-8 -*-
# types
from __future__ import annotations

from typing import Any
from typing import Literal
from typing import MutableMapping
from typing import Protocol
from typing import TypedDict
from typing import Union


class DosingProgram(Protocol):
    """
    Should return a non-negative float representing (approx) how much liquid was moved, in ml.
    """

    def __call__(
        self, ml: float, unit: str, experiment: str, source_of_event: str
    ) -> float:
        ...


MQTTMessagePayload = Union[bytes, bytearray]


class MQTTMessage:
    payload: MQTTMessagePayload
    topic: str
    qos: Literal[0, 1, 2]
    retain: bool
    mid: int


PublishableSettingDataType = Union[str, float, int, bool]


class PublishableSetting(TypedDict, total=False):
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

    datatype: Literal[
        "string",
        "float",
        "integer",
        "json",
        "boolean",
        "Automation",
        "GrowthRate",
        "ODFiltered",
        "Temperature",
    ]
    unit: str
    settable: bool
    persist: bool


class DbmMapping(MutableMapping):
    def __getitem__(self, key: str | bytes) -> bytes:
        """
        Internally, dbm will convert all values to bytes
        """
        ...

    def __setitem__(self, key: str | bytes, value: str | bytes) -> None:
        ...

    def get(self, key: str | bytes, default: Any = None) -> Any:
        ...


JobState = Literal["init", "ready", "sleeping", "disconnected", "lost"]


LedChannel = Literal["A", "B", "C", "D"]
# these are strings! Don't make them ints, since ints suggest we can perform math on them, that's meaningless.
# str suggest symbols, which they are.
PdChannel = Literal["1", "2"]
PwmChannel = Literal["1", "2", "3", "4", "5"]

PdAngle = Literal["45", "90", "135", "180", "REF"]


# All GPIO pins below are BCM numbered
GpioPin = Literal[
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
