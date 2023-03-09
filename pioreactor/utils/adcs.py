# -*- coding: utf-8 -*-
# adc abstraction
from __future__ import annotations

from typing import cast

import busio  # type: ignore

from pioreactor import exc
from pioreactor import hardware
from pioreactor import types as pt
from pioreactor.version import hardware_version_info


class _ADC:
    gain: float = 1

    def read_from_channel(self, channel: pt.AdcChannel) -> pt.AnalogValue:
        raise NotImplementedError

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        raise NotImplementedError

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        raise NotImplementedError

    def check_on_gain(self, value: pt.Voltage, tol=0.85) -> None:
        raise NotImplementedError


class ADS1115_ADC(_ADC):
    DATA_RATE = 128
    ADS1X15_GAIN_THRESHOLDS = {
        2 / 3: (4.096, 6.144),
        1: (2.048, 4.096),
        2: (1.024, 2.048),
        4: (0.512, 1.024),
        8: (0.256, 0.512),
        16: (-1, 0.256),
    }

    ADS1X15_PGA_RANGE = {
        2 / 3: 6.144,
        1: 4.096,
        2: 2.048,
        4: 1.024,
        8: 0.512,
        16: 0.256,
    }
    gain: float = 1.0

    def __init__(self) -> None:
        super().__init__()

        from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore
        from busio import I2C  # type: ignore
        from adafruit_ads1x15.ads1115 import ADS1115 as ADS  # type: ignore

        self.analog_in: dict[int, AnalogIn] = {}

        self._ads = ADS(
            I2C(hardware.SCL, hardware.SDA),
            data_rate=self.DATA_RATE,
            gain=self.gain,
            address=hardware.ADC,
        )
        for channel in (0, 1, 2, 3):
            self.analog_in[channel] = AnalogIn(self._ads, channel)

    def check_on_gain(self, value: pt.Voltage, tol=0.85) -> None:
        for gain, (lb, ub) in self.ADS1X15_GAIN_THRESHOLDS.items():
            if (tol * lb <= value < tol * ub) and (self.gain != gain):
                self.gain = gain
                self.set_ads_gain(gain)
                break

    def set_ads_gain(self, gain: float) -> None:
        self._ads.gain = gain  # this assignment will check to see if the gain is allowed.

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        # from https://github.com/adafruit/Adafruit_CircuitPython_ADS1x15/blob/e33ed60b8cc6bbd565fdf8080f0057965f816c6b/adafruit_ads1x15/analog_in.py#L61
        return cast(pt.AnalogValue, voltage * 32767 / self.ADS1X15_PGA_RANGE[self.gain])

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        # from https://github.com/adafruit/Adafruit_CircuitPython_ADS1x15/blob/e33ed60b8cc6bbd565fdf8080f0057965f816c6b/adafruit_ads1x15/analog_in.py#L61
        return raw / 32767 * self.ADS1X15_PGA_RANGE[self.gain]

    def read_from_channel(self, channel: pt.AdcChannel) -> pt.AnalogValue:
        assert 0 <= channel <= 3
        return self.analog_in[channel].value


class Pico_ADC(_ADC):
    def __init__(self) -> None:
        # set up i2c connection to hardware.ADC
        self.i2c = busio.I2C(hardware.SCL, hardware.SDA)

    def read_from_channel(self, channel: pt.AdcChannel) -> pt.AnalogValue:
        assert 0 <= channel <= 3
        result = bytearray(2)
        try:
            self.i2c.writeto_then_readfrom(
                hardware.ADC, bytes([channel + 4]), result
            )  # + 4 is the i2c pointer offset
            return int.from_bytes(result, byteorder="little", signed=False)
        except OSError:
            raise exc.HardwareNotFoundError(
                f"Unable to find i2c channel {hardware.ADC}. Is the HAT attached? Is the firmware loaded?"
            )

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        return int((voltage / 3.3) * 4095 * 16)

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        return (raw / 4095 / 16) * 3.3

    def check_on_gain(self, value: pt.Voltage, tol=0.85) -> None:
        # pico has no gain.
        pass


ADC = ADS1115_ADC if (0, 0) < hardware_version_info <= (1, 0) else Pico_ADC
