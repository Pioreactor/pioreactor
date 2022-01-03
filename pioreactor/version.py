# -*- coding: utf-8 -*-
from __future__ import annotations


__version__ = "21.1.0"


def _get_hardware_version():
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_ver", "r") as f:
            text = f.read().rstrip("\x00")
            return (int(text[-2]), int(text[-1]))
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env?
        return (0, 1)


hardware_version_info = _get_hardware_version()
software_version_info = tuple(int(c) for c in __version__.split("."))
