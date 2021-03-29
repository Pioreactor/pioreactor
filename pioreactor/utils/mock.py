# -*- coding: utf-8 -*-
# mock pieces for testing
import numpy as np
from adafruit_ads1x15.analog_in import AnalogIn
from pioreactor.config import config


class MockI2C:
    def __init__(self, SCL, SDA):
        pass

    def writeto(self, *args, **kwargs):
        return

    def try_lock(self, *args, **kwargs):
        return True

    def unlock(self, *args, **kwargs):
        pass


class MockAnalogIn(AnalogIn):
    INIT_STATE = 0.2
    state = INIT_STATE
    _counter = 0

    @staticmethod
    def growth_rate(duration_as_seconds):
        return 0.15 / (1 + np.exp(-0.0005 * (duration_as_seconds - 3 * 60 * 60)))

    @property
    def voltage(self):
        import random

        self.state *= np.exp(
            self.growth_rate(
                self._counter
                / config.getfloat("od_config.od_sampling", "samples_per_second")
            )
            / 60
            / 60
            / config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self._counter += 1
        return self.state + self.state / self.INIT_STATE * random.normalvariate(0, 1e-3)


class MockDAC43608:

    _DEVICE_CONFIG = 1
    _STATUS = 2
    _BRDCAST = 3
    A = 8
    B = 9
    C = 10
    D = 11
    E = 12
    F = 13
    G = 14
    H = 15

    def __init__(self, *args, **kwargs):
        pass

    def set_intensity_to(self, channel, intensity):
        assert 0 <= intensity <= 1
        assert channel in list(range(16))
        # TODO: this should update MQTT too
        return

    def power_up(*args):
        pass
