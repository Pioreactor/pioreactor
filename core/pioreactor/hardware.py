# -*- coding: utf-8 -*-
from __future__ import annotations

from os import environ

from pioreactor import exc
from pioreactor import types as pt
from pioreactor.utils import adcs
from pioreactor.version import hardware_version_info
from pioreactor.version import rpi_version_info
from pioreactor.whoami import is_testing_env

#
# All GPIO pins below are BCM numbered

# PWMs
# Heater PWM
HEATER_PWM_TO_PIN: pt.PwmChannel = "5"

# map between PWM channels and GPIO pins
PWM_TO_PIN: dict[pt.PwmChannel, pt.GpioPin] = {
    "1": 17,
    "2": 13,  # hardware PWM1 available
    "3": 16,
    "4": 12,  # hardware PWM0 available
    HEATER_PWM_TO_PIN: 18,  # dedicated to heater
}


# led and button GPIO pins
PCB_LED_PIN: pt.GpioPin = 23
PCB_BUTTON_PIN: pt.GpioPin = 24 if hardware_version_info <= (1, 0) else 4


# hall sensor
HALL_SENSOR_PIN: pt.GpioPin = 25 if hardware_version_info <= (1, 0) else 21


# I2C pins
GPIOCHIP: pt.GpioChip
SDA: pt.I2CPin
SCL: pt.I2CPin

if rpi_version_info.startswith("Raspberry Pi 5"):
    GPIOCHIP = 4
    SDA = 2
    SCL = 3
else:
    GPIOCHIP = 0
    SDA = 2
    SCL = 3

## not used in app
# if hardware_version_info >= (1,1):
#     # SWD, used in HAT version == 1.1
#     SWCLK: pt.GpioPin = 25
#     SWDIO: pt.GpioPin = 24


# I2C channels used
TEMP_ADDRESS = 0x4F
TEMP = TEMP_ADDRESS  # bc


od_optics_setup = environ.get("OPTICS_MOD", "on_board")


class ADCCurrier:
    """
    We don't to initiate the ADCs until we need them, so we curry them using this class, and this keeps all
    the hardware metadata nice and neat and accessible.

    from pioreactor.hardware import ADCs

    adc = ADCs['pd1']()
    reading = adc.read_from_channel()

    """

    def __init__(
        self, adc_driver: type[adcs._I2C_ADC], i2c_address: pt.I2CAddress, adc_channel: pt.AdcChannel
    ):
        self.adc_driver = adc_driver
        self.i2c_address = i2c_address
        self.adc_channel = adc_channel

    def __call__(self) -> adcs._I2C_ADC:
        return self.adc_driver(SCL, SDA, self.i2c_address, self.adc_channel)

    def __repr__(self) -> str:
        return f"ADCCurrier(adc_driver={self.adc_driver.__name__}, i2c_address={hex(self.i2c_address)}, adc_channel={self.adc_channel})"


ADCs: dict[str, ADCCurrier] = {}
if od_optics_setup == "eye_spy":
    ADCs["pd1"] = ADCCurrier(adcs.ADS1114_ADC, 0x48, 0)
    ADCs["pd2"] = ADCCurrier(adcs.ADS1114_ADC, 0x49, 0)

elif od_optics_setup == "on_board":
    if hardware_version_info <= (1, 0):
        ADCs["pd1"] = ADCCurrier(adcs.ADS1115_ADC, 0x48, 1)
        ADCs["pd2"] = ADCCurrier(adcs.ADS1115_ADC, 0x48, 0)
    else:
        ADCs["pd1"] = ADCCurrier(adcs.Pico_ADC, 0x2C, 2)
        ADCs["pd2"] = ADCCurrier(adcs.Pico_ADC, 0x2C, 3)
else:
    raise exc.HardwareNotFoundError()

if hardware_version_info <= (1, 0):
    ADCs["aux"] = ADCCurrier(adcs.ADS1115_ADC, 0x48, 3)
    ADCs["version"] = ADCCurrier(adcs.ADS1115_ADC, 0x48, 2)
else:
    ADCs["aux"] = ADCCurrier(adcs.Pico_ADC, 0x2C, 1)
    ADCs["version"] = ADCCurrier(adcs.Pico_ADC, 0x2C, 0)


DAC_ADDRESS = 0x49 if (0, 0) < hardware_version_info <= (1, 0) else 0x2C
DAC = DAC_ADDRESS  # bc


def is_i2c_device_present(channel: int) -> bool:
    if is_testing_env():
        from pioreactor.utils.mock import MockI2C as I2C
    else:
        from adafruit_blinka.microcontroller.generic_linux.i2c import I2C  # type: ignore

    try:
        I2C(1, mode=I2C.MASTER).writeto(channel, b"")
        return True
    except OSError:
        return False


def is_DAC_present() -> bool:
    return is_i2c_device_present(DAC_ADDRESS)


def is_ADC_present(*args: int) -> bool:
    if args:
        to_check = set(args)
    else:
        to_check = set([adc.i2c_address for adc in ADCs.values()])
    return all(is_i2c_device_present(c) for c in to_check)


def is_heating_pcb_present() -> bool:
    return is_i2c_device_present(TEMP_ADDRESS)


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
    if not is_testing_env():
        AUX_ADC = ADCs["aux"]
    else:
        from pioreactor.utils.mock import Mock_ADC  # type: ignore

        AUX_ADC = ADCCurrier(Mock_ADC, 0x00, 0)

    adc = AUX_ADC()
    slope = 0.134  # from schematic

    return round_to_precision(
        adc.from_raw_to_voltage(adc.read_from_channel()) / slope,
        p=precision,
    )
