# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.whoami import is_testing_env

if is_testing_env():
    from pioreactor.utils.mock import MockI2C as I2C
else:
    from busio import I2C  # type: ignore


from adafruit_bus_device.i2c_device import I2CDevice

from pioreactor.types import GPIO_Pin, PWM_Channel
from pioreactor.version import hardware_version_info

# All GPIO pins below are BCM numbered

PWM_TO_PIN: dict[PWM_Channel, GPIO_Pin] = {
    # map between PCB labels and GPIO pins
    1: 6 if hardware_version_info == (0, 1) else 17,
    2: 13,  # hardware PWM1 available
    3: 16,
    4: 12,  # hardware PWM0 available
    5: 18,  # dedicated to heater
}

# led and button GPIO pins
PCB_LED_PIN: GPIO_Pin = 23
PCB_BUTTON_PIN: GPIO_Pin = 24

# hall sensor
HALL_SENSOR_PIN: GPIO_Pin = 25

# Heater PWM
HEATER_PWM_TO_PIN: PWM_Channel = 5


# I2C GPIO pins
SDA: GPIO_Pin = 2
SCL: GPIO_Pin = 3


# I2C channels used
ADC = hex(72)  # 0x48
DAC = hex(73)  # 0x49
TEMP = hex(79)  # 0x4f


def is_HAT_present():
    with I2C(SCL, SDA) as i2c:
        try:
            I2CDevice(i2c, ADC, probe=True)
            return True
        except ValueError:
            return False


def is_heating_pcb_present():
    with I2C(SCL, SDA) as i2c:
        try:
            I2CDevice(i2c, TEMP, probe=True)
            return True
        except ValueError:
            return False
