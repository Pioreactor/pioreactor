# -*- coding: utf-8 -*-
# dacs.py
from __future__ import annotations

from typing import cast

import busio  # type: ignore

from pioreactor import hardware
from pioreactor.exc import HardwareNotFoundError
from pioreactor.types import FloatBetween0and100
from pioreactor.version import hardware_version_info


class _DAC:
    A = 0
    B = 1
    C = 2
    D = 3

    def set_intensity_to(self, channel: int, intensity: FloatBetween0and100) -> None:
        # float is a value between 0 and 100 inclusive
        pass


class DAC43608_DAC(_DAC):
    A = 8
    B = 9
    C = 10
    D = 11

    def __init__(self) -> None:
        from DAC43608 import DAC43608

        self.dac = DAC43608(address=hardware.DAC)

    def set_intensity_to(self, channel: int, intensity: FloatBetween0and100) -> None:
        from DAC43608 import Channel

        channel = cast(Channel, channel)
        if intensity == 0.0:
            self.dac.power_down(channel)
        else:
            self.dac.power_up(channel)
            self.dac.set_intensity_to(channel, intensity / 100.0)  # type: ignore


class Pico_DAC(_DAC):
    """
    The DAC is an 8-bit controller implemented in the Pico firmware. See pico-build repository for details.
    """

    A = 0
    B = 1
    C = 2
    D = 3

    def __init__(self) -> None:
        # set up i2c connection to hardware.DAC
        self.i2c = busio.I2C(hardware.SCL, hardware.SDA)

    def set_intensity_to(self, channel: int, intensity: FloatBetween0and100) -> None:
        try:
            # to 8 bit integer
            eight_bit = round((intensity / 100) * 255)
            self.i2c.writeto(hardware.DAC, bytes([channel, eight_bit]))
        except OSError:
            raise HardwareNotFoundError(
                f"Unable to find i2c channel {hardware.DAC}. Is the HAT attached? Is the firmware loaded?"
            )


DAC = DAC43608_DAC if (0, 0) < hardware_version_info <= (1, 0) else Pico_DAC
