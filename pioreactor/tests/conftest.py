# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import fake_rpi  # type: ignore
import pytest

# Replace libraries by fake RPi ones

sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO
sys.modules["smbus"] = fake_rpi.smbus  # Fake smbus (I2C)

fake_rpi.toggle_print(False)


# allow Blinka to think we are an Rpi:
# https://github.com/adafruit/Adafruit_Python_PlatformDetect/blob/75f69806222fbaf8535130ed2eacd07b06b1a298/adafruit_platformdetect/board.py
os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"  # RaspberryPi
os.environ["BLINKA_FORCEBOARD"] = "RASPBERRY_PI_3A_PLUS"  # Raspberry Pi 3 Model A Plus Rev 1.0


@pytest.fixture(autouse=True)
def run_around_tests():
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistant_storage

    with local_intermittent_storage("led_locks") as cache:
        for key in cache.keys():
            del cache[key]

    with local_intermittent_storage("pwm_locks") as cache:
        for key in cache.keys():
            del cache[key]

    with local_intermittent_storage("leds") as cache:
        for key in cache.keys():
            del cache[key]

    with local_persistant_storage("current_od_calibration") as cache:
        for key in cache.keys():
            del cache[key]

    yield
