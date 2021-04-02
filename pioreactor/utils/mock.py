# -*- coding: utf-8 -*-
# mock pieces for testing
import numpy as np
from adafruit_ads1x15.analog_in import AnalogIn
from pioreactor.config import config
from pioreactor.pubsub import subscribe_and_callback
import logging


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
    INIT_STATE = 0.1
    state = INIT_STATE
    _counter = 0

    def __init__(self, *args, **kwargs):

        # subscribe to dosing events
        from pioreactor.whoami import get_unit_name, get_latest_experiment_name

        subscribe_and_callback(
            self.react_to_dosing,
            f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/dosing_events",
        )

    def react_to_dosing(self, message):
        import json

        payload = json.loads(message.payload)

        if payload["event"] not in ["add_media", "add_alt_media"]:
            return

        self.state = self.state * (1 - (payload["volume_change"] / 14))

    @staticmethod
    def growth_rate(duration_as_seconds):
        return 0.15 / (1 + np.exp(-0.0005 * (duration_as_seconds - 2 * 60 * 60)))

    @property
    def voltage(self):
        import random

        gr = self.growth_rate(
            self._counter / config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self.state *= np.exp(
            gr / 60 / 60 / config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self._counter += 1
        logging.getLogger("MockAnalogIn").debug(f"state={self.state}, gr={gr}")
        return self.state + random.normalvariate(0, self.state * 0.025)


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
