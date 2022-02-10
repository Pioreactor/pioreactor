# -*- coding: utf-8 -*-
from __future__ import annotations

from msgspec import Struct

import pioreactor.types as pt


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
