# -*- coding: utf-8 -*-
# mock pieces for testing
from json import loads
from pioreactor.config import config
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.whoami import am_I_active_worker, is_testing_env
import random


class MockI2C:
    def __init__(self, SCL, SDA):
        pass

    def writeto(self, *args, **kwargs):
        return

    def try_lock(self, *args, **kwargs):
        return True

    def unlock(self, *args, **kwargs):
        pass


class MockAnalogIn:
    INIT_STATE = 0.1
    state = INIT_STATE
    _counter = 0

    def __init__(self, ads, channel, **kwargs):
        from pioreactor.whoami import get_unit_name, get_latest_experiment_name

        # import pandas as pd
        # self.source = pd.read_csv(f"/Users/camerondavidson-pilon/code/pioreactor/demo_od{channel}.csv", index_col=0)

        # subscribe to dosing events
        assert channel in [0, 1], "channel must be in 0, 1"
        subscribe_and_callback(
            self.react_to_dosing,
            f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/dosing_events",
        )
        self.max_gr = 0.25 + 0.1 * random.random()
        self.scale_factor = 0.00025 + 0.00005 * random.random()
        self.lag = 8 * 60 * 60 - 120 * random.random()

    def react_to_dosing(self, message):

        payload = loads(message.payload)

        if payload["event"] not in ["add_media", "add_alt_media"]:
            return
        self.state = self.state * (1 - (payload["volume_change"] / 14))

    def growth_rate(self, duration_as_seconds):
        import numpy as np

        return self.max_gr / (
            1 + np.exp(-self.scale_factor * (duration_as_seconds - self.lag))
        )

    @property
    def voltage(self):
        import random
        import numpy as np

        self.gr = self.growth_rate(
            self._counter / config.getfloat("od_config", "samples_per_second")
        )
        self.state *= np.exp(
            self.gr
            / 60
            / 60
            / config.getfloat("od_config", "samples_per_second")
            / 25  # divide by 25 from oversampling_count
        )
        self._counter += 1
        return self.state + random.normalvariate(0, sigma=self.state * 0.001)

    @property
    def value(self):
        print(self.gr)
        return round(self.voltage * 2 ** 17)


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
        assert 0 <= intensity <= 1, "intensity should be between 0 and 1"
        assert channel in list(range(8, 16)), "register should be in 8 to 15"
        # TODO: this should update MQTT too
        return

    def power_up(*args):
        pass

    def power_down(*args):
        pass


class MockTMP1075:
    def __init__(*args):
        pass

    def get_temperature(self):
        import time, math, random

        return 3 * math.sin(0.1 * time.time() / 60) + 25 + 0.2 * random.random()


if am_I_active_worker() or is_testing_env():

    from rpi_hardware_pwm import HardwarePWM

    class MockHardwarePWM(HardwarePWM):
        def __init__(self, pwm_channel, hz):
            self.pwm_channel = pwm_channel
            self._hz = hz
            self.pwm_dir = ""

        def is_overlay_loaded(self):
            return True

        def is_export_writable(self):
            return True

        def does_pwmX_exists(self):
            return True

        def echo(self, m, fil):
            pass
