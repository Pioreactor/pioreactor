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

        self.STATE = self.STATE * random.lognormvariate(0.15 * 5 / 60 / 60, 0.0002)
        return self.STATE
