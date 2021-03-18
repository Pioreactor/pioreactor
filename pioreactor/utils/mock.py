# -*- coding: utf-8 -*-
# mock pieces for testing
from adafruit_ads1x15.analog_in import AnalogIn


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

    @property
    def voltage(self):
        import random

        self.STATE = self.STATE * random.lognormvariate(0.15 * 5 / 60 / 60, 0.0001)
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
