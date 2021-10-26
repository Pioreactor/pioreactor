# -*- coding: utf-8 -*-


# Replace libraries by fake RPi ones
import sys
import fake_rpi  # type: ignore

sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO
sys.modules["smbus"] = fake_rpi.smbus  # Fake smbus (I2C)

fake_rpi.toggle_print(False)
