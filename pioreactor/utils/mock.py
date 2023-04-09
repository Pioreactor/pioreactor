# -*- coding: utf-8 -*-
# mock pieces for testing
from __future__ import annotations

import random
from typing import Any

import pioreactor.types as pt
from pioreactor.config import config
from pioreactor.utils.adcs import _ADC
from pioreactor.utils.dacs import _DAC
from pioreactor.whoami import is_testing_env


class MockI2C:
    def __init__(self, SCL: int, SDA: int) -> None:
        pass

    def writeto(self, *args, **kwargs) -> None:
        return

    def try_lock(self, *args, **kwargs) -> bool:
        return True

    def unlock(self, *args, **kwargs) -> None:
        pass

    def readfrom_into(self, add, buffer, start=0, end=1_000_000):
        pass

    def __enter__(self) -> MockI2C:
        return self

    def __exit__(self, *args: Any) -> None:
        return


class Mock_ADC(_ADC):
    INIT_STATE = 0.01
    state = INIT_STATE
    _counter = 0.0
    OFFSET = 0.03

    def __init__(self, *args, **kwargs) -> None:
        self.max_gr = 0.25 + 0.1 * random.random()
        self.scale_factor = 0.00035 + 0.00005 * random.random()
        self.lag = 2 * 60 * 60 - 1 * 60 * 60 * random.random()

    def read_from_channel(self, channel: pt.AdcChannel):
        from pioreactor.utils import local_intermittent_storage
        import random
        import numpy as np

        with local_intermittent_storage("leds") as leds:
            is_ir_on = float(leds.get(config.get("leds_reverse", "IR"), 0.0)) > 0.0

        if not is_ir_on:
            return self.OFFSET

        am_i_REF = str(channel + 1) == config.get("od_config.photodiode_channel_reverse", "REF")

        if am_i_REF:
            return (0.1 + random.normalvariate(0, sigma=0.001)) / 2**10 * 40 + self.OFFSET
        else:
            self.gr = self.growth_rate(
                self._counter / config.getfloat("od_config", "samples_per_second"), am_i_REF
            )
            self.state *= np.exp(
                self.gr
                / 60
                / 60
                / config.getfloat("od_config", "samples_per_second")
                / 25  # divide by 25 from oversampling_count
            )
            self._counter += 1.0 / 25.0  # divide by 25 from oversampling_count
            return self.from_voltage_to_raw(
                self.state + random.normalvariate(0, sigma=self.state * 0.01) + self.OFFSET
            )

    def growth_rate(self, duration_as_seconds: float, am_i_REF: bool) -> float:
        if am_i_REF:
            return 0

        import numpy as np

        return (
            self.max_gr
            / (1 + np.exp(-self.scale_factor * (duration_as_seconds - self.lag)))
            * (1 - 1 / (1 + np.exp(-self.scale_factor * 2 * (duration_as_seconds - 3 * self.lag))))
        )

    def check_on_gain(self, *args, **kwargs) -> None:
        pass

    def from_voltage_to_raw(self, voltage) -> int:
        return round(voltage * 32767 / 4.096)

    def from_raw_to_voltage(self, raw) -> float:
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
    def __init__(*args, address=0x4F) -> None:
        pass

    def get_temperature(self) -> float:
        import time, math, random

        return 3 * math.sin(0.1 * time.time() / 60) + 25 + 0.2 * random.random()


if is_testing_env():
    from rpi_hardware_pwm import HardwarePWM

    class MockHardwarePWM(HardwarePWM):
        def __init__(self, pwm_channel: int, hz: float) -> None:
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
