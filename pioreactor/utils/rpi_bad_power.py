# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Optional

"""
MIT License

Copyright (c) 2020 Xiaonan Shen, Cameron Davidson-Pilon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
"""
Utilities for reading under voltage bit from the official Raspberry Pi Kernel.
Modified from https://github.com/shenxn/rpi-bad-power
Minimal Kernel needed is 4.14+
"""

HWMON_NAME = "rpi_volt"

SYSFILE_HWMON_DIR = "/sys/class/hwmon"
SYSFILE_HWMON_FILE = "in0_lcrit_alarm"
SYSFILE_LEGACY = "/sys/devices/platform/soc/soc:firmware/get_throttled"

UNDERVOLTAGE_STICKY_BIT = 1 << 16


def get_rpi_volt_hwmon() -> Optional[str]:
    """Find rpi_volt hwmon device."""
    try:
        hwmons = os.listdir(SYSFILE_HWMON_DIR)
    except FileNotFoundError:
        return None

    for hwmon in hwmons:
        name_file = os.path.join(SYSFILE_HWMON_DIR, hwmon, "name")
        if os.path.isfile(name_file):
            with open(name_file) as file:
                hwmon_name = file.read().strip()
            if hwmon_name == HWMON_NAME:
                return os.path.join(SYSFILE_HWMON_DIR, hwmon)

    return None


class UnderVoltage:
    """Read under voltage status."""

    def get(self) -> bool:
        """Get under voltage status."""
        raise NotImplementedError


class UnderVoltageNew(UnderVoltage):
    """Read under voltage status from new entry."""

    def __init__(self, hwmon: str):
        """Initialize the under voltage class."""
        self._hwmon = hwmon

    def get(self) -> bool:
        """Get under voltage status."""
        # Use new hwmon entry
        with open(os.path.join(self._hwmon, SYSFILE_HWMON_FILE)) as file:
            bit = file.read()[:-1]
        return bit == "1"


class UnderVoltageLegacy(UnderVoltage):
    """Read under voltage status from legacy entry."""

    def get(self) -> bool:
        """Get under voltage status."""
        # Using legacy get_throttled entry
        with open(SYSFILE_LEGACY) as file:
            throttled = file.read()[:-1]
        return int(throttled, base=16) & UNDERVOLTAGE_STICKY_BIT == UNDERVOLTAGE_STICKY_BIT


def new_under_voltage() -> Optional[UnderVoltage]:
    """Create new UnderVoltage object."""
    hwmon = get_rpi_volt_hwmon()
    if hwmon:
        return UnderVoltageNew(hwmon)
    if os.path.isfile(SYSFILE_LEGACY):  # support older kernel
        return UnderVoltageLegacy()
    return None
