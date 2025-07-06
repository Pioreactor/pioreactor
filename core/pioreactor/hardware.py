# -*- coding: utf-8 -*-
from __future__ import annotations

from os import environ

from pioreactor.types import AdcChannel
from pioreactor.types import GpioChip
from pioreactor.types import GpioPin
from pioreactor.types import I2CPin
from pioreactor.types import PdChannel
from pioreactor.types import PwmChannel
from pioreactor.version import hardware_version_info
from pioreactor.version import rpi_version_info
from pioreactor.whoami import is_testing_env

# All GPIO pins below are BCM numbered

# PWMs
# Heater PWM
HEATER_PWM_TO_PIN: PwmChannel = "5"

# map between PWM channels and GPIO pins
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


# I2C pins
GPIOCHIP: GpioChip
SDA: I2CPin
SCL: I2CPin

if rpi_version_info.startswith("Raspberry Pi 5"):
    GPIOCHIP = 4
    SDA = 2
    SCL = 3
else:
    GPIOCHIP = 0
    SDA = 2
    SCL = 3

if hardware_version_info >= (1, 1):
    # SWD, used in HAT version >= 1.1
    SWCLK: GpioPin = 25
    SWDIO: GpioPin = 24


# I2C channels used
ADC = 0x48 if (0, 0) < hardware_version_info <= (1, 0) else 0x2C  # As of 24.8.22, =44. Prior it was 0x30=48.
DAC = 0x49 if (0, 0) < hardware_version_info <= (1, 0) else 0x2C  # As of 24.8.22, =44. Prior it was 0x30=48
TEMP = 0x4F


# ADC map of function to hardware ADC channel
ADC_CHANNEL_FUNCS: dict[str | PdChannel, AdcChannel]

if is_testing_env():
    ADC_CHANNEL_FUNCS = {
        "1": 2,
        "2": 3,
        "version": 0,
        "aux": 1,
    }
elif hardware_version_info <= (0, 1):  # alpha
    ADC_CHANNEL_FUNCS = {
        "1": 0,
        "2": 1,
        "version": 2,
        "aux": 3,
    }
elif hardware_version_info <= (1, 0):  # beta
    ADC_CHANNEL_FUNCS = {
        "1": 1,
        "2": 0,
        "version": 2,
        "aux": 3,
    }
else:  # prod
    ADC_CHANNEL_FUNCS = {
        "1": 2,
        "2": 3,
        "version": 0,
        "aux": 1,
    }


def is_i2c_device_present(channel: int) -> bool:
    if is_testing_env():
        from pioreactor.utils.mock import MockI2C as I2C
    else:
        from busio import I2C  # type: ignore

    from adafruit_bus_device.i2c_device import I2CDevice  # type: ignore

    with I2C(SCL, SDA) as i2c:
        try:
            I2CDevice(i2c, channel, probe=True)
            return True
        except ValueError:
            return False


def is_DAC_present() -> bool:
    return is_i2c_device_present(DAC)


def is_ADC_present() -> bool:
    return is_i2c_device_present(ADC)


def is_heating_pcb_present() -> bool:
    return is_i2c_device_present(TEMP)


def is_HAT_present() -> bool:
    if is_testing_env() or (environ.get("HAT_PRESENT", "0") == "1"):
        return True

    try:
        with open("/proc/device-tree/hat/vendor", "r") as f:
            vendor = f.readline().strip("\x00")

        with open("/proc/device-tree/hat/product_id", "r") as f:
            product_id = f.readline().strip("\x00")

        return vendor == "Pioreactor Inc." and product_id == "0x0001"
    except FileNotFoundError:
        return False


def round_to_precision(x: float, p: float) -> float:
    """
    Ex: round_to_precision(x, 0.5) rounds to the nearest 0.5 (half-integer interval)
    """
    y = round(x / p) * p
    return y


def voltage_in_aux(precision: float = 0.1) -> float:
    # Warning: this _can_ mess with OD readings if running at the same time.
    if not is_testing_env():
        from pioreactor.utils.adcs import ADC as ADC_class
    else:
        from pioreactor.utils.mock import Mock_ADC as ADC_class  # type: ignore

    slope = 0.134  # from schematic

    adc = ADC_class()  # type: ignore
    return round_to_precision(
        adc.from_raw_to_voltage(adc.read_from_channel(ADC_CHANNEL_FUNCS["aux"])) / slope,
        p=precision,
    )
