# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any

__version__ = "21.12.0"


def get_hardware_version():
    return "0.0"


hardware_version_diff: dict[str, Any]

if get_hardware_version() == "0.0":
    hardware_version_diff = {"ads1x15_version": "1"}
else:
    raise KeyError("hardware version not found")
