# -*- coding: utf-8 -*-
# adc abstraction
from __future__ import annotations

import struct
import time
from typing import Final

try:
    # Debian/Raspberry Pi: prefer smbus2
    from smbus2 import SMBus
except Exception:
    # Fallback to smbus if smbus2 isn't available
    from smbus import SMBus  # type: ignore

from busio import I2C  # type: ignore
from pioreactor import exc
from pioreactor import hardware
from pioreactor import types as pt


class _ADC:
    gain: float = 1

    def read_from_channel(self, channel: pt.AdcChannel) -> pt.AnalogValue:
        raise NotImplementedError

    def from_voltage_to_raw(self, voltage: pt.Voltage) -> pt.AnalogValue:
        raise NotImplementedError

    def from_raw_to_voltage(self, raw: pt.AnalogValue) -> pt.Voltage:
        raise NotImplementedError

    def check_on_gain(self, value: pt.Voltage, tol: float = 0.85) -> None:
        raise NotImplementedError

    def from_voltage_to_raw_precise(self, voltage: pt.Voltage) -> pt.AnalogValue:
        """Convert a voltage to a raw ADC value with precision."""
        # Default implementation; subclasses may override
        return self.from_voltage_to_raw(voltage)


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

    def read_from_channel(self, channel: pt.AdcChannel) -> pt.AnalogValue:
        assert 0 <= channel <= 3
        return self.analog_in[channel].value


class Pico_ADC(_ADC):
    def __init__(self) -> None:
        # set up i2c connection to hardware.ADC
        self.i2c = I2C(hardware.SCL, hardware.SDA)
        if self.get_firmware_version() >= (0, 4):
            self.scale = 32
        else:
            self.scale = 16

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

    def get_firmware_version(self) -> tuple[int, int]:
        try:
            result = bytearray(2)
            self.i2c.writeto_then_readfrom(hardware.ADC, bytes([0x08]), result)
            return (result[1], result[0])
        except OSError:
            raise exc.HardwareNotFoundError(
                f"Unable to find i2c channel {hardware.ADC}. Is the HAT attached? Is the firmware loaded?"
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


class ADS1114_ADC(_ADC):
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
        2 / 3: (-6.144, 6.144),
        1.0: (-4.096, 4.096),
        2.0: (-2.048, 2.048),
        4.0: (-1.024, 1.024),
        8.0: (-0.512, 0.512),
        16.0: (-0.256, 0.256),
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

    def __init__(self, i2c_addr: int) -> None:
        super().__init__()
        i2c_bus = 1
        self._bus = SMBus(i2c_bus)
        self._addr = i2c_addr
        # Cache current DR and PGA fields
        self._dr_bits = self._DR_CODE[self.DATA_RATE]
        self.set_ads_gain(self.gain)  # also writes base config

    def check_on_gain(self, value, tol: float = 0.85) -> None:
        # Auto-select gain that keeps the value inside a comfortable portion of its FSR
        for gain, (lb, ub) in self.ADS1X14_GAIN_THRESHOLDS.items():
            if (tol * lb <= value < tol * ub) and (self.gain != gain):
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

    def read_from_channel(self, channel) -> int:
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
        msb, lsb = self._bus.read_i2c_block_data(self._addr, self._CONVERSION, 2)
        value = struct.unpack(">h", bytes((msb, lsb)))[0]
        return int(value)

    # --- Private helpers ---

    def _read_config_ready(self) -> bool:
        msb, lsb = self._bus.read_i2c_block_data(self._addr, self._CONFIG, 2)
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
        self._bus.write_i2c_block_data(self._addr, reg, data)

    def __del__(self) -> None:
        try:
            self._bus.close()
        except Exception:
            pass


class MultiplexADS1114_ADC(_ADC):
    """
    Wrap two ADS1114 devices (0x48 and 0x49) behind a single ADC interface.

    channel:
      "1" or 1 -> read from device at addr_ch1 (default 0x48)
      "2" or 2 -> read from device at addr_ch2 (default 0x49)
    """

    # Keep identical constants to the single-device class
    DATA_RATE = ADS1114_ADC.DATA_RATE
    ADS1X14_PGA_RANGE = ADS1114_ADC.ADS1X14_PGA_RANGE
    ADS1X14_GAIN_THRESHOLDS = ADS1114_ADC.ADS1X14_GAIN_THRESHOLDS
    ADS1X15_GAIN_THRESHOLDS = ADS1X14_GAIN_THRESHOLDS  # compat alias
    gain: float = 1.0  # shared gain across both chips

    def __init__(
        self,
    ) -> None:
        super().__init__()
        assert isinstance(hardware.ADC, tuple)
        self._adc1 = ADS1114_ADC(i2c_addr=hardware.ADC[0])
        self._adc2 = ADS1114_ADC(i2c_addr=hardware.ADC[1])
        # Ensure both have identical config
        self.set_ads_gain(self.gain)

    def _pick(self, channel) -> ADS1114_ADC:
        ch = str(channel).strip()
        if ch == "1":
            return self._adc1
        if ch == "2":
            return self._adc2
        raise ValueError("channel must be '1' or '2'.")

    # ---- Interface required by _ADC ----

    def read_from_channel(self, channel) -> int:
        adc = self._pick(channel)
        # Underlying ADS1114 has only one pair; its read ignores channel.
        return adc.read_from_channel(channel)

    def set_ads_gain(self, gain: float) -> None:
        # Update both devices — they must remain identical
        # Reuse the single-device validation
        self._adc1.set_ads_gain(gain)
        self._adc2.set_ads_gain(gain)
        self.gain = gain  # keep shared state

    def from_voltage_to_raw(self, voltage):
        return int(voltage * 32767 / self.ADS1X14_PGA_RANGE[self.gain])

    def from_voltage_to_raw_precise(self, voltage):
        return voltage * 32767 / self.ADS1X14_PGA_RANGE[self.gain]

    def from_raw_to_voltage(self, raw):
        return raw / 32767 * self.ADS1X14_PGA_RANGE[self.gain]

    def check_on_gain(self, value, tol: float = 0.85) -> None:
        # Pick a gain that fits the measured value and apply to BOTH devices.
        for gain, (lb, ub) in self.ADS1X14_GAIN_THRESHOLDS.items():
            if (tol * lb <= value < tol * ub) and (self.gain != gain):
                self.set_ads_gain(gain)
                break
