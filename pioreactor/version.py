# -*- coding: utf-8 -*-
from __future__ import annotations

# Append ".dev" if a dev version
__version__ = "22.12.2.dev"


def _get_hardware_version() -> tuple[int, int] | tuple[int, int, str]:
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_ver", "r") as f:
            text = f.read().rstrip("\x00")
            return (int(text[-2]), int(text[-1]))
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env, or EEPROM not written.
        return (0, 0, "dev")


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
    if hardware_version_info >= (1, 1):

        import busio
        from pioreactor.hardware import SCL, SDA, ADC

        i2c = busio.I2C(SCL, SDA)
        result = bytearray(2)
        i2c.writeto_then_readfrom(ADC, bytes([0x08]), result)
        return result[0], result[1]

    else:
        return (0, 0)


def tuple_to_text(t: tuple) -> str:
    return ".".join(map(str, t))


def safe_int(s):
    try:
        return int(s)
    except ValueError:
        return s


hardware_version_info = _get_hardware_version()
software_version_info = tuple(safe_int(c) for c in __version__.split("."))
serial_number = _get_serial_number()
