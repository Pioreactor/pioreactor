# -*- coding: utf-8 -*-

# All GPIO pins below are BCM

PWM_TO_PIN = {
    # map between PCB labels and GPIO pins
    1: 6,
    2: 13,  # hardware PWM1 available
    3: 16,
    4: 12,  # hardware PWM0 available
    5: 18,
}

# led and button GPIO pins
PCB_LED_PIN = 23
PCB_BUTTON_PIN = 24

# I2C GPIO pins
SDA = 2
SCL = 3


# I2C channels used
ADC = hex(72)
DAC = hex(73)
TEMP = hex(79)
