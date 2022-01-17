# -*- coding: utf-8 -*-
# types
from __future__ import annotations
from typing import Literal, MutableMapping, TypedDict, Union, Any

MQTTMessagePayload = Union[bytes, bytearray]


class MQTTMessage:
    payload: MQTTMessagePayload
    topic: str
    qos: Literal[0, 1, 2]
    retain: bool
    mid: int


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

    unit (optional):
        a string representing what the unit suffix is

    settable:
        a bool representing if the attribute can be changed over MQTT

    persist (optional):
        a bool representing if the attr should be cleared when the job cleans up. Default False.

    """

    datatype: Literal["string", "float", "integer", "json", "boolean"]
    unit: str
    settable: bool
    persist: bool


class DbmMapping(MutableMapping):
    def __getitem__(self, key: str) -> bytes:
        """
        Internally, dbm will convert all values to bytes
        """
        ...

    def __setitem__(self, key: str, value: str | bytes) -> None:
        ...

    def get(self, key: str, default: Any = None) -> Any:
        ...


JobState = Literal["init", "ready", "sleeping", "disconnected", "lost"]


LED_Channel = Literal["A", "B", "C", "D"]

# these are strings! Don't make them ints, since ints suggest we can perform math on them, that's meaningless.
# str suggest symbols, which they are.
PD_Channel = Literal["1", "2"]
PWM_Channel = Literal["1", "2", "3", "4", "5"]


# All GPIO pins below are BCM numbered
GPIO_Pin = Literal[
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
