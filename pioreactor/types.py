# -*- coding: utf-8 -*-
# types
from __future__ import annotations
from typing import Literal, MutableMapping


class DbmMapping(MutableMapping):
    def __getitem__(self, key: str) -> bytes:
        """
        Internally, dbm will convert all values to bytes
        """
        ...

    def __setitem__(self, key: str, value: str | bytes) -> None:
        ...


JobState = Literal["init", "ready", "sleeping", "disconnected", "lost"]


LED_Channel = Literal["A", "B", "C", "D"]

PD_Channel = Literal[
    "1", "2"
]  # these are strings! Don't make them ints, since ints suggest we can perform math on them, that's meaningless. str suggest symbols, which they are.

PWM_Channel = Literal[1, 2, 3, 4, 5]

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
