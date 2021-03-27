# -*- coding: utf-8 -*-
# mock pieces for testing
from adafruit_ads1x15.analog_in import AnalogIn
from pioreactor import config


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
    STATE = 0.2
    TARGET = 0.15

    @property
    def voltage(self):
        import random

        self.STATE = self.STATE * random.lognormvariate(
            self.TARGET
            / 60
            / 60
            / config.getfloat("od_config.od_sampling", "samples_per_second"),
            0.000001,
        )
        return self.STATE


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
        return

    def power_up(*args):
        pass
