# -*- coding: utf-8 -*-
from __future__ import annotations

import os

# Append "dev" if a dev version
# Append "rc0" if a rc version
__version__ = "23.10.5"


def _get_hardware_version() -> tuple[int, int] | tuple[int, int, str]:
    if os.environ.get("HARDWARE") is not None:
        # ex: > HARDWARE=1.1 pio ...
        return int(os.environ["HARDWARE"].split(".")[0]), int(os.environ["HARDWARE"].split(".")[1])

    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_ver", "r") as f:
            text = f.read().rstrip("\x00")
            return (int(text[-2]), int(text[-1]))
    except FileNotFoundError:
        # no eeprom? Probably dev board with no EEPROM, or testing env, or EEPROM not written.
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


def get_firmware_version() -> tuple[int, int]:
    if os.environ.get("FIRMWARE") is not None:
        # ex: > FIRMWARE=1.1 pio ...

        return tuple(int(_) for _ in os.environ["FIRMWARE"].split("."))  # type: ignore

    if hardware_version_info >= (1, 1):
        try:
            import busio  # type: ignore
            from pioreactor.hardware import SCL, SDA, ADC

            i2c = busio.I2C(SCL, SDA)
            result = bytearray(2)
            i2c.writeto_then_readfrom(ADC, bytes([0x08]), result)
            return (result[1], result[0])
        except Exception:
            return (0, 0)

    else:
        return (0, 0)


def tuple_to_text(t: tuple) -> str:
    return ".".join(map(str, t))


def safe_int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return s


hardware_version_info = _get_hardware_version()
software_version_info = tuple(safe_int(c) for c in __version__.split("."))
serial_number = _get_serial_number()
