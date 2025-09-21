# -*- coding: utf-8 -*-
"""
Hardware configuration loader and compatibility layer.

Overview
- Hardware config is defined by user-editable YAML files only.
- Mods (subsystems) are layered by precedence: hats/<hat_version> -> models/<model>/<version>.
  Later layer overrides earlier. Paths are under ~/.pioreactor/hardware/.
- Required mods must exist and will raise if missing keys.

Paths
- Base: ~/.pioreactor/hardware
  - hats/<hat_version>/<mod>.yaml     # wiring/electrical details tied to HAT
  - models/<model>/<version>/<mod>.yaml  # model intent and capability opt-in

Layering rules
- For a given mod, the loader deep-merges (dict-wise) files in this order:
  1) hats/<hat_version>/<mod>.yaml
  2) models/<model>/<version>/<mod>.yaml
  Later keys override earlier ones.

Back-compat exports
- Keep existing module attributes used across the codebase:
  - ADCs: dict with keys 'pd1', 'pd2', 'aux', 'version' mapping to curried ADC drivers
  - PWM_TO_PIN: map from PWM channel ("1".."5") to BCM pin
  - HEATER_PWM_TO_PIN: PWM channel string dedicated to heater
  - GPIOCHIP: integer chip index (0 on most; 4 on RPi 5)
  - TEMP_ADDRESS, DAC_ADDRESS (and TEMP, DAC aliases)
- PWM_CONTROLLER is exposed for forward-compatibility (e.g., 'rpi_gpio' vs 'hat_mcu'),
  but is not yet used elsewhere.

YAML schemas (initial scope)
- pwm.yaml
  - controller: rpi_gpio | hat_mcu
  - heater_pwm_channel: "5"
  - pwm_to_pin: {"1": 17, "2": 13, "3": 16, "4": 12, "5": 18}
- adc.yaml
  - pd1|pd2|aux|version:
      driver: ads1115 | ads1114 | pico
      address: 0x.. or int
      channel: int
- dac.yaml
  - address: 0x..
- temp.yaml
  - address: 0x..
- gpio.yaml
  - pcb_led_pin: int
  - pcb_button_pin: int
  - hall_sensor_pin: int
  - sda_pin: int (default 2)
  - scl_pin: int (default 3)

"""
from __future__ import annotations

from os import environ
from pathlib import Path
from typing import Any

from msgspec.yaml import decode as yaml_decode
from pioreactor import exc
from pioreactor import types as pt
from pioreactor.utils import adcs
from pioreactor.version import hardware_version_info
from pioreactor.version import rpi_version_info
from pioreactor.whoami import get_pioreactor_model
from pioreactor.whoami import is_testing_env


def _hat_version_text() -> str:
    try:
        major, minor = hardware_version_info[:2]
    except Exception:
        major, minor = (0, 0)
    return f"{major}.{minor}"


def _load_yaml_if_exists(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return yaml_decode(path.read_bytes()) or {}
        except Exception as e:
            raise exc.HardwareError(f"Failed to parse YAML at {path}: {e}")
    return {}


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge b into a and return a new dict."""
    out: dict[str, Any] = {**a}
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_layered_mod_config(mod: str) -> dict[str, Any]:
    """Load one mod's YAML by layering hats -> model.

    Later layer (model) overrides earlier (hat). Files are optional; missing
    keys will be caught when materializing constants below.
    """
    base = Path(environ["DOT_PIOREACTOR"]) / "hardware"

    model = get_pioreactor_model()
    model_dir = base / "models" / model.model_name / model.model_version
    hat_dir = base / "hats" / _hat_version_text()
    model_file = model_dir / f"{mod}.yaml"

    data: dict[str, Any] = {}
    data = _deep_merge(data, _load_yaml_if_exists(hat_dir / f"{mod}.yaml"))
    data = _deep_merge(data, _load_yaml_if_exists(model_file))
    return data


# PWMs (loaded from YAML)
_pwm_cfg = get_layered_mod_config("pwm")

# pwm.controller for future-proofing (rpi_gpio | hat_mcu). Not currently used elsewhere.
PWM_CONTROLLER: str | None = _pwm_cfg.get("controller")

# Heater PWM channel
HEATER_PWM_TO_PIN: pt.PwmChannel = str(_pwm_cfg["heater_pwm_channel"])  # type: ignore

# map between PWM channels and GPIO pins
PWM_TO_PIN: dict[pt.PwmChannel, pt.GpioPin] = {str(k): v for k, v in _pwm_cfg["pwm_to_pin"].items()}  # type: ignore


# I2C pins and misc GPIO
SDA: pt.I2CPin
SCL: pt.I2CPin

GPIOCHIP: pt.GpioChip = 4 if rpi_version_info.startswith("Raspberry Pi 5") else 0

_gpio_cfg = get_layered_mod_config("gpio")

SDA = int(_gpio_cfg["sda_pin"])
SCL = int(_gpio_cfg["scl_pin"])

PCB_LED_PIN: pt.GpioPin = int(_gpio_cfg["pcb_led_pin"])
PCB_BUTTON_PIN: pt.GpioPin = int(_gpio_cfg["pcb_button_pin"])
HALL_SENSOR_PIN: pt.GpioPin = int(_gpio_cfg["hall_sensor_pin"])

_temp_cfg = get_layered_mod_config("temp")
TEMP_ADDRESS = int(_temp_cfg["address"])
TEMP = TEMP_ADDRESS  # bc


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


_ADC_DRIVER_LUT: dict[str, type[adcs._I2C_ADC]] = {
    "ads1115": adcs.ADS1115_ADC,
    "ads1114": adcs.ADS1114_ADC,
    "pico": adcs.Pico_ADC,
}


def _build_adc_currier_from_cfg(entry: dict[str, Any], context_key: str) -> ADCCurrier:
    try:
        driver_key = str(entry["driver"]).lower()
        driver = _ADC_DRIVER_LUT[driver_key]
        addr = int(entry["address"])  # supports decimal or hex
        channel = int(entry["channel"])  # 0..3
    except KeyError as e:
        raise exc.HardwareNotFoundError(
            f"Missing key {e.args[0]!r} in adc configuration for '{context_key}'."
        ) from e
    except Exception as e:
        raise exc.HardwareError(
            f"Invalid adc configuration for '{context_key}': {type(e).__name__}: {e}"
        ) from e
    return ADCCurrier(driver, addr, channel)


_adc_cfg = get_layered_mod_config("adc")
ADCs: dict[str, ADCCurrier] = {}
for key in ("pd1", "pd2", "aux", "version"):
    if key in _adc_cfg:
        ADCs[key] = _build_adc_currier_from_cfg(_adc_cfg[key], key)
    else:
        raise exc.HardwareNotFoundError(
            f"Missing adc configuration for '{key}'. Ensure hardware/models/<model>/<version>/adc.yaml or overlays provide it."
        )


_dac_cfg = get_layered_mod_config("dac")
DAC_ADDRESS = int(_dac_cfg["address"])

DAC = DAC_ADDRESS  # bc


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
