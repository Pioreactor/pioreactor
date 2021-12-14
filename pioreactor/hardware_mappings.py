# -*- coding: utf-8 -*-
from pioreactor.version import hardware_version_info

# All GPIO pins below are BCM numbered

PWM_TO_PIN = {
    # map between PCB labels and GPIO pins
    1: 6 if hardware_version_info == (0, 1) else 17,
    2: 13,  # hardware PWM1 available
    3: 16,
    4: 12,  # hardware PWM0 available
    5: 18,  # dedicated to heater
}

# led and button GPIO pins
PCB_LED_PIN = 23
PCB_BUTTON_PIN = 24

# hall sensor
HALL_SENSOR_PIN = 25

# Heater PWM
HEATER_PWM_TO_PIN = 5


# I2C GPIO pins
SDA = 2
SCL = 3


# I2C channels used
ADC = hex(72)  # 0x48
DAC = hex(73)  # 0x49
TEMP = hex(79)  # 0x4f
