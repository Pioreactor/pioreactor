# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.types import AdcChannel
from pioreactor.types import GpioPin
from pioreactor.types import PdChannel
from pioreactor.types import PwmChannel
from pioreactor.version import hardware_version_info
from pioreactor.whoami import is_testing_env

# All GPIO pins below are BCM numbered

# Heater PWM
HEATER_PWM_TO_PIN: PwmChannel = "5"

# map between PCB labels and GPIO pins
PWM_TO_PIN: dict[PwmChannel, GpioPin] = {
    "1": 6 if hardware_version_info == (0, 1) else 17,
    "2": 13,  # hardware PWM1 available
    "3": 16,
    "4": 12,  # hardware PWM0 available
    HEATER_PWM_TO_PIN: 18,  # dedicated to heater
}

# led and button GPIO pins
PCB_LED_PIN: GpioPin = 23
PCB_BUTTON_PIN: GpioPin = 24 if (0, 0) < hardware_version_info <= (1, 0) else 4

# hall sensor
HALL_SENSOR_PIN: GpioPin = 25 if (0, 0) < hardware_version_info <= (1, 0) else 21

# I2C GPIO pins
SDA: GpioPin = 2
SCL: GpioPin = 3

# I2C channels used
ADC = 0x48 if (0, 0) < hardware_version_info <= (1, 0) else 0x30
DAC = 0x49 if (0, 0) < hardware_version_info <= (1, 0) else 0x30
TEMP = 0x4F

# ADC map of function to hardware ADC channel
ADC_CHANNEL_FUNCS: dict[str | PdChannel, AdcChannel]

if (0, 0) < hardware_version_info <= (1, 0):
    ADC_CHANNEL_FUNCS = {
        "1": 0 if hardware_version_info <= (0, 1) else 1,
        "2": 1 if hardware_version_info <= (0, 1) else 0,
        "version": 2,
        "aux": 3,
    }
else:
    ADC_CHANNEL_FUNCS = {
        "1": 2,
        "2": 3,
        "version": 0,
        "aux": 1,
    }


def is_HAT_present() -> bool:
    if is_testing_env():
        from pioreactor.utils.mock import MockI2C as I2C
    else:
        from busio import I2C  # type: ignore

    from adafruit_bus_device.i2c_device import I2CDevice  # type: ignore

    with I2C(SCL, SDA) as i2c:
        try:
            I2CDevice(i2c, DAC, probe=True)
            return True
        except ValueError:
            return False


def is_heating_pcb_present() -> bool:
    if is_testing_env():
        from pioreactor.utils.mock import MockI2C as I2C
    else:
        from busio import I2C  # type: ignore

    from adafruit_bus_device.i2c_device import I2CDevice  # type: ignore

    with I2C(SCL, SDA) as i2c:
        try:
            I2CDevice(i2c, TEMP, probe=True)
            return True
        except ValueError:
            return False


def round_to_precision(x: float, p: float) -> float:
    """
    Ex: round_to_precision(x, 0.5) rounds to the nearest 0.5 (half-integer interval)
    """
    y = round(x / p) * p
    return y


def voltage_in_aux(precision=0.1) -> float:
    # Warning: this _can_ mess with OD readings if running at the same time.
    if not is_testing_env():
        from pioreactor.utils.adcs import ADC as ADC_class
    else:
        from pioreactor.utils.mock import Mock_ADC as ADC_class  # type: ignore

    slope = 0.134  # from schematic

    adc = ADC_class()
    return round_to_precision(
        adc.from_raw_to_voltage(adc.read_from_channel(ADC_CHANNEL_FUNCS["aux"])) / slope,
        p=precision,
    )
