# -*- coding: utf-8 -*-
# mock pieces for testing
import math
import random
from typing import Any
from typing import cast

import pioreactor.types as pt
from pioreactor.config import config
from pioreactor.utils.adcs import _I2C_ADC
from pioreactor.utils.dacs import _DAC
from pioreactor.whoami import is_testing_env


class MockI2C:
    MASTER = 0
    SLAVE = 1
    _baudrate = None
    _mode = None
    _i2c_bus = None

    def __init__(self, port: int, mode: int = MASTER) -> None:
        pass

    def writeto(self, *args: Any, **kwargs: Any) -> None:
        return

    def try_lock(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def unlock(self, *args: Any, **kwargs: Any) -> None:
        pass

    def readfrom_into(self, add: int, buffer: bytearray, start: int = 0, end: int = 1_000_000) -> None:
        pass

    def __enter__(self) -> "MockI2C":
        return self

    def __exit__(self, *args: Any) -> None:
        return


class Mock_ADC(_I2C_ADC):
    INIT_STATE = 0.01
    OFFSET = 0.002
    gain = 1

    RESIDUAL_RHO = 0.02
    RESIDUAL_CV = 0.0056
    SIGMA_FLOOR = 0.0
    SHOCK_PROBABILITY = 0.0073

    # Keep rare shocks subtle for the low-noise family.
    SHOCK_SIGMA_MULTIPLIER_MIN = 2.0
    SHOCK_SIGMA_MULTIPLIER_MAX = 5.0

    def __init__(self, adc_channel: int, i2c_addr: int, *args: Any, **kwargs: Any) -> None:
        self._counter = 0.0
        self.state = self.INIT_STATE

        self.max_gr = 0  # 0.25 + 0.1 * random.random()
        self.start_time = 10.0 * 60.0
        self.end_time = self.start_time + 60.0 * 60.0 * 8.0
        self.up_scale = 0.01
        self.down_scale = 0.003

        self.adc_channel = adc_channel
        self.i2c_addr = i2c_addr

        # Static per-reactor sensitivity offset: LogNormal(meanlog=0, sdlog=0.071)
        self.unit_scale = random.lognormvariate(0.0, 0.071)

        # AR(1) residual state in voltage space.
        self._residual = 0.0

        # Give the REF channel a stable but not perfectly identical baseline.
        self._reference_voltage = 0.100 + random.normalvariate(0.0, 0.0003)

    def read_from_channel(self) -> float:
        from pioreactor.utils import local_intermittent_storage

        samples_per_second = config.getfloat("od_reading.config", "samples_per_second")
        oversampling_count = 40.0

        with local_intermittent_storage("leds") as leds:
            ir_intensity = cast(float | int | str, leds.get(config.get("leds_reverse", "IR"), 0.0))
            is_ir_on = float(ir_intensity) > 0.0

        if not is_ir_on:
            return self.OFFSET

        am_i_REF = self.adc_channel == 1  # see _get_ADCS in od_reading.py

        if am_i_REF:
            ref_voltage = self._reference_voltage + random.normalvariate(0.0, 0.00015)
            return self.from_voltage_to_raw(ref_voltage)

        dt = 1.0 / samples_per_second / oversampling_count
        elapsed_seconds = self._counter / samples_per_second

        self.state *= math.exp(self.growth_rate(elapsed_seconds, am_i_REF) * dt / 60 / 60)
        self._counter += 1.0 / oversampling_count

        clean_signal = self.unit_scale * self.state
        sigma = self._sigma(clean_signal) * math.sqrt(oversampling_count)

        innovation = math.sqrt(1.0 - self.RESIDUAL_RHO**2) * sigma * random.normalvariate(0.0, 1.0)
        self._residual = self.RESIDUAL_RHO * self._residual + innovation

        shock = 0.0
        if random.random() < self.SHOCK_PROBABILITY:
            shock_scale = random.uniform(
                self.SHOCK_SIGMA_MULTIPLIER_MIN,
                self.SHOCK_SIGMA_MULTIPLIER_MAX,
            )
            shock = shock_scale * sigma * random.normalvariate(0.0, 1.0)

        observed_voltage = clean_signal + self._residual + shock + self.OFFSET
        return self.from_voltage_to_raw(max(0.0, observed_voltage))

    def _sigma(self, signal_voltage: float) -> float:
        return math.sqrt(self.SIGMA_FLOOR**2 + (self.RESIDUAL_CV * signal_voltage) ** 2)

    def growth_rate(self, duration_as_seconds: float, am_i_REF: bool) -> float:
        if am_i_REF:
            return 0.0

        ramp_up = 1.0 / (1.0 + math.exp(-self.up_scale * (duration_as_seconds - self.start_time)))
        ramp_down = 1.0 / (1.0 + math.exp(self.down_scale * (duration_as_seconds - self.end_time)))
        return self.max_gr * ramp_up * ramp_down

    def check_on_gain(self, *args: Any, **kwargs: Any) -> None:
        pass

    def set_ads_gain(self, gain: float) -> None:
        pass

    def from_voltage_to_raw(self, voltage: float) -> int:
        return round(voltage * 32767 / 4.096)

    def from_voltage_to_raw_precise(self, voltage: float) -> float:
        return voltage * 32767 / 4.096

    def from_raw_to_voltage(self, raw: float) -> float:
        return 4.096 * raw / 32767


class Mock_DAC(_DAC):
    A = 8
    B = 9
    C = 10
    D = 11
    E = 12
    F = 13
    G = 14
    H = 15

    def set_intensity_to(self, channel: int, intensity: float) -> None:
        assert 0.0 <= intensity <= 100.0, "intensity should be between 0 and 100"
        assert channel in list(range(8, 16)), "register should be in 8 to 15"
        return


class MockTMP1075:
    def __init__(self, address: int = 0x4F) -> None:
        pass

    def get_temperature(self) -> float:
        import time, math, random

        return 3 * math.sin(0.1 * time.time() / 60) + 25 + 0.2 * random.random()


class MockPWMOutputDevice:
    def __init__(self, pin: pt.GpioPin, initial_dc: float = 0.0, frequency: float = 100) -> None:
        self.pin = pin
        self._dc = initial_dc
        self.frequency = frequency
        self.open = True

    def start(self, initial_dc: pt.FloatBetween0and100) -> None:
        if not self.open:
            raise IOError()

    def off(self) -> None:
        self.dc = 0.0

    @property
    def dc(self) -> float:
        return self._dc

    @dc.setter
    def dc(self, dc: float) -> None:
        if self.open:
            self._dc = dc
        else:
            raise IOError()

    def close(self) -> None:
        self.open = False


class MockCallback:
    def cancel(self) -> None:
        pass


class MockHandle:
    def __and__(self, other: object) -> int:
        return 1


class MockRpmCalculator:
    ALWAYS_RETURN_RPM = config.getfloat("stirring.config", "initial_target_rpm")

    def setup(self) -> None:
        pass

    def estimate(self, seconds_to_observe: float = 0.1) -> float:
        import time

        time.sleep(seconds_to_observe)
        return self.ALWAYS_RETURN_RPM

    def clean_up(self) -> None:
        pass


if is_testing_env():
    from rpi_hardware_pwm import HardwarePWM

    class MockHardwarePWM(HardwarePWM):
        def __init__(self, pwm_channel: int, hz: float, chip: int = 0) -> None:
            self.pwm_channel = pwm_channel
            self._hz = hz
            self.pwm_dir = ""

        def is_overlay_loaded(self) -> bool:
            return True

        def is_export_writable(self) -> bool:
            return True

        def does_pwmX_exists(self) -> bool:
            return True

        def echo(self, m: int, fil: str) -> None:
            pass
