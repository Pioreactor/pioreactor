# -*- coding: utf-8 -*-

# All GPIO pins below are BCM

PWM_TO_PIN = {
    # map between PCB labels and GPIO pins
    0: 6,
    1: 13,  # hardware PWM1 available
    2: 16,
    3: 12,  # hardware PWM0 available
    4: 18,
}

# led and button GPIO pins
PCB_LED_PIN = 23
PCB_BUTTON_PIN = 24

HALL_SENSOR_PIN = 14

# I2C GPIO pins
SDA = 2
SCL = 3
