# -*- coding: utf-8 -*-
from __future__ import annotations

from adafruit_blinka.microcontroller.generic_linux.i2c import I2C


class TMP1075:
    """
    Driver for the TI TMP1075 temperature sensor.
    See datasheet: http://www.ti.com/lit/ds/symlink/tmp1075.pdf

    """

    TEMP_REGISTER = bytearray([0x00])
    # CONFIG_REGISTER = bytearray([0x01])

    def __init__(self, address: int = 0x4F) -> None:
        self.i2c = I2C(1, mode=I2C.MASTER)
        self.address = address

    def get_temperature(self) -> float:
        b = bytearray(2)
        self.i2c.writeto_then_readfrom(self.address, self.TEMP_REGISTER, b)
        return ((b[0] << 4) + (b[1] >> 4)) * 0.0625

    @property
    def temperature(self) -> float:
        """alias for get_temperature"""
        return self.get_temperature()
