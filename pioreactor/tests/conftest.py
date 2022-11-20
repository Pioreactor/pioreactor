# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

import fake_rpi  # type: ignore
import pytest

# Replace libraries by fake RPi ones

sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO
sys.modules["smbus"] = fake_rpi.smbus  # Fake smbus (I2C)

fake_rpi.toggle_print(False)


@pytest.fixture(autouse=True)
def run_around_tests():
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistant_storage

    with local_intermittent_storage("led_locks") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_intermittent_storage("pwm_locks") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_intermittent_storage("leds") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_persistant_storage("current_od_calibration") as cache:
        for key in cache.iterkeys():
            del cache[key]

    yield
