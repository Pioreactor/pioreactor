# -*- coding: utf-8 -*-
from __future__ import annotations


__version__ = "22.12.2"


def _get_hardware_version() -> tuple[int, int]:
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_ver", "r") as f:
            text = f.read().rstrip("\x00")
            return (int(text[-2]), int(text[-1]))
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env, or EEPROM not written.
        return (0, 0)


def _get_serial_number() -> str:
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/uuid", "r") as f:
            text = f.read().rstrip("\x00")
            return text
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env, or EEPROM not written.
        return "00000000-0000-0000-0000-000000000000"


def tuple_to_text(t: tuple) -> str:
    return ".".join(map(str, t))


hardware_version_info = _get_hardware_version()
software_version_info = tuple(int(c) for c in __version__.split("."))
serial_number = _get_serial_number()
