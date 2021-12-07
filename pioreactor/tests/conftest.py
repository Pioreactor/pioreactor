# -*- coding: utf-8 -*-

import pytest

# Replace libraries by fake RPi ones
import sys
import fake_rpi  # type: ignore

sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO
sys.modules["smbus"] = fake_rpi.smbus  # Fake smbus (I2C)

fake_rpi.toggle_print(False)


@pytest.fixture(autouse=True)
def run_around_tests():
    from pioreactor.utils import local_intermittent_storage

    with local_intermittent_storage("pio_jobs_running") as cache:
        for key in cache.keys():
            del cache[key]

    with local_intermittent_storage("led_locks") as cache:
        for key in cache.keys():
            del cache[key]

    yield
