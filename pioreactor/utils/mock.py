# -*- coding: utf-8 -*-
# mock pieces for testing
from json import loads
from adafruit_ads1x15.analog_in import AnalogIn
from pioreactor.config import config
from pioreactor.pubsub import subscribe_and_callback
from rpi_hardware_pwm import HardwarePWM
import random

random.seed(10)


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

    def __init__(self, ads, channel, **kwargs):
        from pioreactor.whoami import get_unit_name, get_latest_experiment_name

        # import pandas as pd
        # self.source = pd.read_csv(f"/Users/camerondavidson-pilon/code/pioreactor/demo_od{channel}.csv", index_col=0)

        # subscribe to dosing events
        subscribe_and_callback(
            self.react_to_dosing,
            f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/dosing_events",
        )

    def react_to_dosing(self, message):

        payload = loads(message.payload)

        if payload["event"] not in ["add_media", "add_alt_media"]:
            return
        self.state = self.state * (1 - (payload["volume_change"] / 14))

    @staticmethod
    def growth_rate(duration_as_seconds):
        import numpy as np

        return 0.25 / (1 + np.exp(-0.00025 * (duration_as_seconds - 8 * 60 * 60)))

    @property
    def voltage(self):
        import random
        import numpy as np

        self.gr = self.growth_rate(
            self._counter / config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self.state *= np.exp(
            self.gr
            / 60
            / 60
            / config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self._counter += 1
        return self.state + random.normalvariate(0, sigma=self.state * 0.01)


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


class MockHardwarePWM(HardwarePWM):
    def is_overlay_loaded(self):
        return True

    def is_export_writable(self):
        return True

    def does_pwmX_exists(self):
        return True

    def echo(self, m, fil):
        pass
