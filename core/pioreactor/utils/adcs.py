# -*- coding: utf-8 -*-
# adc abstraction
from __future__ import annotations

import struct
import time
from typing import Final
from typing import Protocol
from typing import runtime_checkable

try:
    # Debian/Raspberry Pi: prefer smbus2
    from smbus2 import SMBus
except Exception:
    # Fallback to smbus if smbus2 isn't available
    from smbus import SMBus  # type: ignore

from busio import I2C  # type: ignore
from pioreactor import exc
from pioreactor import types as pt


@runtime_checkable
class _I2C_ADC(Protocol):
    """Structural protocol for I2C ADC drivers."""

    gain: float
    i2c_addr: int

    def __init__(
        self, scl: pt.I2CPin, sda: pt.I2CPin, i2c_addr: pt.I2CAddress, adc_channel: pt.AdcChannel
    ) -> None:
        ...

    def read_from_channel(self) -> pt.AnalogValue:
        ...

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        ...

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        ...

    def check_on_gain(self, value: pt.Voltage, tol: float = 0.85) -> None:
        ...

    def from_voltage_to_raw_precise(self, voltage: pt.Voltage) -> pt.AnalogValue:
        ...


class ADS1115_ADC:
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

    def __init__(
        self, scl: pt.I2CPin, sda: pt.I2CPin, i2c_addr: pt.I2CAddress, adc_channel: pt.AdcChannel
    ) -> None:
        from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore
        from adafruit_ads1x15.ads1115 import ADS1115 as ADS  # type: ignore

        assert 0 <= adc_channel <= 3
        self.adc_channel = adc_channel
        self.i2c_addr = i2c_addr
        self._ads = ADS(
            I2C(scl, sda),
            data_rate=self.DATA_RATE,
            gain=self.gain,
            address=self.i2c_addr,
        )
        self.analog_in = AnalogIn(self._ads, self.adc_channel)

    def check_on_gain(self, value: pt.Voltage, tol: float = 0.85) -> None:
        for gain, (lb, ub) in self.ADS1X15_GAIN_THRESHOLDS.items():
            if (tol * lb <= value < tol * ub) and (self.gain != gain):
                self.gain = gain
                self.set_ads_gain(gain)
                break

    def set_ads_gain(self, gain: float) -> None:
        self._ads.gain = gain  # this assignment will check to see if the gain is allowed.

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        # from https://github.com/adafruit/Adafruit_CircuitPython_ADS1x15/blob/e33ed60b8cc6bbd565fdf8080f0057965f816c6b/adafruit_ads1x15/analog_in.py#L61
        return int(voltage * 32767 / self.ADS1X15_PGA_RANGE[self.gain])

    def from_voltage_to_raw_precise(self, voltage: pt.Voltage) -> pt.AnalogValue:
        return voltage * 32767 / self.ADS1X15_PGA_RANGE[self.gain]

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        # from https://github.com/adafruit/Adafruit_CircuitPython_ADS1x15/blob/e33ed60b8cc6bbd565fdf8080f0057965f816c6b/adafruit_ads1x15/analog_in.py#L61
        return raw / 32767 * self.ADS1X15_PGA_RANGE[self.gain]

    def read_from_channel(self) -> pt.AnalogValue:
        return self.analog_in.value


class Pico_ADC:
    gain: float = 1.0  # Pico ADC has fixed range; expose for interface

    def __init__(
        self, scl: pt.I2CPin, sda: pt.I2CPin, i2c_addr: pt.I2CAddress, adc_channel: pt.AdcChannel
    ) -> None:
        # set up i2c connection to the Pico ADC at PD1 address (shared)
        self.i2c = I2C(scl, sda)
        self.i2c_addr = i2c_addr
        assert 0 <= adc_channel <= 3
        self.adc_channel = adc_channel
        if self.get_firmware_version() >= (0, 4):
            self.scale = 32
        else:
            self.scale = 16

    def read_from_channel(self) -> pt.AnalogValue:
        result = bytearray(2)
        try:
            self.i2c.writeto_then_readfrom(
                self.i2c_addr, bytes([self.adc_channel + 4]), result
            )  # + 4 is the i2c pointer offset
            return int.from_bytes(result, byteorder="little", signed=False)
        except OSError:
            raise exc.HardwareNotFoundError(
                f"Unable to find i2c address {self.i2c_addr}. Is the HAT attached? Is the firmware loaded?"
            )

    def get_firmware_version(self) -> tuple[int, int]:
        try:
            result = bytearray(2)
            self.i2c.writeto_then_readfrom(self.i2c_addr, bytes([0x08]), result)
            return (result[1], result[0])
        except OSError:
            raise exc.HardwareNotFoundError(
                f"Unable to find i2c address {self.i2c_addr}. Is the HAT attached? Is the firmware loaded?"
            )

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        return int((voltage / 3.3) * 4095 * self.scale)

    def from_voltage_to_raw_precise(self, voltage: pt.Voltage) -> float:
        return (voltage / 3.3) * 4095 * self.scale

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        return (raw / 4095 / self.scale) * 3.3

    def check_on_gain(self, value: pt.Voltage, tol: float = 0.85) -> None:
        # pico has no gain.
        pass


class ADS1114_ADC:
    """
    ADS1114 16-bit ADC over I2C.

    Notes:
      * ADS1114 has a *single* input pair (AIN0, AIN1). For single-ended reads,
        tie AIN1 to GND in hardware and read AIN0.
      * This driver uses single-shot conversions by default.

    """

    _CONVERSION: Final[int] = 0x00
    _CONFIG: Final[int] = 0x01

    # Data rate (samples/s); conversion time ~= 1/DR
    DATA_RATE: Final[int] = 128

    # Map "gain" (PGA multiplier like 2/3, 1, 2, 4, 8, 16) -> full-scale range (±volts).
    # Table 7-1 in the datasheet lists these FSR values for the ADS1114 PGA.
    ADS1X14_PGA_RANGE: dict[float, float] = {
        2 / 3: 6.144,
        1.0: 4.096,
        2.0: 2.048,
        4.0: 1.024,
        8.0: 0.512,
        16.0: 0.256,
    }

    # Threshold windows used by check_on_gain(): (lower_bound, upper_bound) in volts.
    ADS1X14_GAIN_THRESHOLDS: dict[float, tuple[float, float]] = {
        2 / 3: (4.096, 6.144),
        1: (2.048, 4.096),
        2: (1.024, 2.048),
        4: (0.512, 1.024),
        8: (0.256, 0.512),
        16: (-1, 0.256),
    }

    # Gain -> PGA bitfield (Config[11:9]) per datasheet
    _PGA_BITS: Final[dict[float, int]] = {
        2 / 3: 0b000,  # ±6.144 V
        1.0: 0b001,  # ±4.096 V
        2.0: 0b010,  # ±2.048 V
        4.0: 0b011,  # ±1.024 V
        8.0: 0b100,  # ±0.512 V
        16.0: 0b101,  # ±0.256 V (also 110/111 map to the same FSR)
    }

    # DR code (Config[7:5]) per datasheet
    _DR_CODE: Final[dict[int, int]] = {
        8: 0b000,
        16: 0b001,
        32: 0b010,
        64: 0b011,
        128: 0b100,
        250: 0b101,
        475: 0b110,
        860: 0b111,
    }

    # Comparator disabled (COMP_QUE = 11), active-low, non-latching, traditional
    _COMP_BITS: Final[int] = 0x0003  # bits [1:0] = 11; bits [4:2] left at reset (0)

    gain: float = 1.0  # default to ±4.096 V

    def __init__(
        self, scl: pt.I2CPin, sda: pt.I2CPin, i2c_addr: pt.I2CAddress, adc_channel: pt.AdcChannel
    ) -> None:
        # SMBUS doesn't use scl or sda directly, it opens up /dev/i2c-1 in the linux space
        i2c_bus = 1
        self._bus = SMBus(i2c_bus)
        self.i2c_addr = i2c_addr
        assert adc_channel == 0
        self.adc_channel = adc_channel
        # Cache current DR and PGA fields
        self._dr_bits = self._DR_CODE[self.DATA_RATE]
        self.set_ads_gain(self.gain)  # also writes base config

    def check_on_gain(self, value, tol: float = 0.85) -> None:
        # Auto-select gain that keeps the value inside a comfortable portion of its FSR
        for gain, (lb, ub) in self.ADS1X14_GAIN_THRESHOLDS.items():
            if (tol * lb <= value < tol * ub) and (self.gain != gain):
                print(f"ADS1114: changing gain from {self.gain} to {gain}")
                self.gain = gain
                self.set_ads_gain(gain)
                break

    def set_ads_gain(self, gain: float) -> None:
        """Apply a new PGA gain (updates device CONFIG)."""
        if gain not in self._PGA_BITS:
            raise ValueError(f"Unsupported ADS1114 gain: {gain}")
        self.gain = gain
        cfg = self._build_config(start=False)  # do not start a conversion here
        self._write_register(self._CONFIG, cfg)

    def from_voltage_to_raw(self, voltage):
        # 16-bit two's complement, FS code = +32767 for +FS
        return int(voltage * 32767 / self.ADS1X14_PGA_RANGE[self.gain])

    def from_voltage_to_raw_precise(self, voltage):
        return voltage * 32767 / self.ADS1X14_PGA_RANGE[self.gain]

    def from_raw_to_voltage(self, raw):
        return raw / 32767 * self.ADS1X14_PGA_RANGE[self.gain]

    def read_from_channel(self) -> int:
        """
        Trigger a single conversion and return the raw 16-bit signed integer.

        ADS1114 has only one channel pair (AIN0-AIN1). `channel` is ignored but
        kept for interface compatibility with other ADCs.
        """
        # Start a single-shot (or update continuous) conversion
        cfg = self._build_config(start=True)
        self._write_register(self._CONFIG, cfg)

        # Poll OS bit (Config[15]) until conversion completes
        # At 128 SPS, max ~7.8 ms; include a tiny sleep to avoid busy loop
        for _ in range(50):
            if self._read_config_ready():
                break
            time.sleep(0.001)
        else:
            # If we somehow never saw OS=1, fall through and still read conversion
            pass

        # Read conversion register (MSB first), convert to signed
        msb, lsb = self._bus.read_i2c_block_data(self.i2c_addr, self._CONVERSION, 2)
        value = struct.unpack(">h", bytes((msb, lsb)))[0]
        return int(value)

    # --- Private helpers ---

    def _read_config_ready(self) -> bool:
        msb, lsb = self._bus.read_i2c_block_data(self.i2c_addr, self._CONFIG, 2)
        cfg = (msb << 8) | lsb
        return bool(cfg & (1 << 15))  # OS bit

    def _build_config(self, *, start: bool) -> int:
        # Bit 15: OS (write 1 to start in single-shot, reads back 0 while converting)
        os_bit = 1 if start else 0

        # Bits 14:12 are RESERVED on ADS1114 -> write 000b
        reserved_14_12 = 0

        # PGA bits [11:9]
        pga_bits = self._PGA_BITS[self.gain] & 0b111

        # MODE bit [8]: 1 = single-shot, 0 = continuous
        mode_bit = 1

        # DR bits [7:5]
        dr_bits = self._dr_bits & 0b111

        # Comparator/control bits [4:0] (we disable comparator)
        comp_bits = self._COMP_BITS & 0x1F

        cfg = (
            (os_bit << 15)
            | (reserved_14_12 << 12)
            | (pga_bits << 9)
            | (mode_bit << 8)
            | (dr_bits << 5)
            | comp_bits
        )
        return cfg & 0xFFFF

    def _write_register(self, reg: int, value: int) -> None:
        data = [(value >> 8) & 0xFF, value & 0xFF]
        self._bus.write_i2c_block_data(self.i2c_addr, reg, data)

    def __del__(self) -> None:
        try:
            self._bus.close()
        except Exception:
            pass
