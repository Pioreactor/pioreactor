# -*- coding: utf-8 -*-
from __future__ import annotations

import os

# pioreactor version
# Append ".dev0" if a dev version
# Append "rc0" if a rc version
# No zero padding!
__version__ = "25.9.18"


def get_hardware_version() -> tuple[int, int] | tuple[int, int, str]:
    if os.environ.get("HARDWARE") is not None:
        # ex: > HARDWARE=1.1 pio ...
        return int(os.environ["HARDWARE"].split(".")[0]), int(os.environ["HARDWARE"].split(".")[1])

    elif os.environ.get("TESTING", "") == "1":  # hack
        return (1, 2)

    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_ver", "r") as f:
            text = f.read().rstrip("\x00")
            return (int(text[-2]), int(text[-1]))
    except FileNotFoundError:
        # no eeprom? Probably dev board with no EEPROM, or testing env, or EEPROM not written, or cable exists between HAT and Pi -> signal degradation.
        return (0, 0)


def get_product_from_id() -> str:
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/product_id", "r") as f:
            id_ = int(f.read().rstrip("\x00"), 16)
            return {1: "Pioreactor HAT"}.get(id_, "Unknown")
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env, or EEPROM not written.
        return "Unknown"


def get_serial_number() -> str:
    try:
        # check version in /proc/device-tree/hat/
        with open("/proc/device-tree/hat/uuid", "r") as f:
            text = f.read().rstrip("\x00")
            return text
    except FileNotFoundError:
        # no eeprom? Probably the first dev boards, or testing env, or EEPROM not written.
        return "00000000-0000-0000-0000-000000000000"


def get_rpi_machine() -> str:
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip().rstrip("\x00")
    except FileNotFoundError:
        return "Raspberry Pi 3"


def get_firmware_version() -> tuple[int, int]:
    if os.environ.get("FIRMWARE") is not None:
        # ex: > FIRMWARE=1.1 pio ...

        return tuple(int(_) for _ in os.environ["FIRMWARE"].split("."))  # type: ignore

    # Compare hardware versions using tuples to avoid lexicographic issues.
    if hardware_version_info >= (1, 1):
        try:
            from adafruit_blinka.microcontroller.generic_linux.i2c import I2C
            from pioreactor.hardware import get_adc_curriers

            result = bytearray(2)
            version_adc = get_adc_curriers()["version"]
            I2C(1, mode=I2C.MASTER).writeto_then_readfrom(version_adc.i2c_address, bytes([0x08]), result)
            return (result[1], result[0])
        except Exception:
            return (0, 0)

    else:
        return (0, 0)


def tuple_to_text(t: tuple) -> str:
    return ".".join(map(str, t))


def version_text_to_tuple(s: str) -> tuple[int, int]:
    return tuple((safe_int(_) for _ in s.split(".")))  # type: ignore


def safe_int(s) -> int:
    try:
        return int(s)
    except (ValueError, TypeError):
        return s


hardware_version_info = get_hardware_version()
software_version_info = version_text_to_tuple(__version__)
serial_number = get_serial_number()
rpi_version_info = get_rpi_machine()
