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

YAML schemas
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

import sys
import warnings
from functools import cache
from os import environ
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

from msgspec.yaml import decode as yaml_decode
from pioreactor import exc
from pioreactor import types as pt
from pioreactor.utils import adcs
from pioreactor.version import hardware_version_info
from pioreactor.version import rpi_version_info
from pioreactor.version import tuple_to_text
from pioreactor.whoami import get_pioreactor_model
from pioreactor.whoami import is_testing_env


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

    try:
        model = get_pioreactor_model()
    except exc.NoModelAssignedError:
        # some default?
        from pioreactor.models import PIOREACTOR_40ml__v1_5

        model = PIOREACTOR_40ml__v1_5

    model_dir = base / "models" / model.model_name / model.model_version
    hat_dir = base / "hats" / tuple_to_text(hardware_version_info)
    model_file = model_dir / f"{mod}.yaml"

    data: dict[str, Any] = {}
    data = _deep_merge(data, _load_yaml_if_exists(hat_dir / f"{mod}.yaml"))
    data = _deep_merge(data, _load_yaml_if_exists(model_file))
    return data


@cache
def determine_gpiochip() -> pt.GpioChip:
    """Return the GPIO chip index for the current Raspberry Pi."""

    return cast(pt.GpioChip, 4 if rpi_version_info.startswith("Raspberry Pi 5") else 0)


@cache
def _load_pwm_cfg() -> dict[str, Any]:
    return get_layered_mod_config("pwm")


@cache
def get_pwm_controller() -> str | None:
    """Return the configured PWM controller type (e.g., 'rpi_gpio' or 'hat_mcu')."""

    return cast(str | None, _load_pwm_cfg().get("controller"))


@cache
def get_heater_pwm_channel() -> pt.PwmChannel:
    return cast(pt.PwmChannel, str(_load_pwm_cfg()["heater_pwm_channel"]))


@cache
def get_pwm_to_pin_map() -> dict[pt.PwmChannel, pt.GpioPin]:
    raw_mapping = _load_pwm_cfg()["pwm_to_pin"]
    if not isinstance(raw_mapping, dict):
        raise exc.HardwareError("Expected 'pwm_to_pin' to be a mapping in pwm configuration.")
    return {cast(pt.PwmChannel, str(k)): cast(pt.GpioPin, int(v)) for k, v in raw_mapping.items()}


@cache
def _load_gpio_cfg() -> dict[str, Any]:
    return get_layered_mod_config("gpio")


@cache
def get_sda_pin() -> pt.I2CPin:
    return cast(pt.I2CPin, int(_load_gpio_cfg()["sda_pin"]))


@cache
def get_scl_pin() -> pt.I2CPin:
    return cast(pt.I2CPin, int(_load_gpio_cfg()["scl_pin"]))


@cache
def get_pcb_led_pin() -> pt.GpioPin:
    return cast(pt.GpioPin, int(_load_gpio_cfg()["pcb_led_pin"]))


@cache
def get_pcb_button_pin() -> pt.GpioPin:
    return cast(pt.GpioPin, int(_load_gpio_cfg()["pcb_button_pin"]))


@cache
def get_hall_sensor_pin() -> pt.GpioPin:
    return cast(pt.GpioPin, int(_load_gpio_cfg()["hall_sensor_pin"]))


@cache
def _load_temp_cfg() -> dict[str, Any]:
    return get_layered_mod_config("temp")


@cache
def get_temp_address() -> int:
    return int(_load_temp_cfg()["address"])


# ADCS


class ADCCurrier:
    """
    We don't to initiate the ADCs until we need them, so we curry them using this class, and this keeps all
    the hardware metadata nice and neat and accessible.

    from pioreactor.hardware import get_adc_curriers

    adc = get_adc_curriers()['pd1']()
    reading = adc.read_from_channel()

    """

    def __init__(
        self, adc_driver: type[adcs._I2C_ADC], i2c_address: pt.I2CAddress, adc_channel: pt.AdcChannel
    ):
        self.adc_driver = adc_driver
        self.i2c_address = i2c_address
        self.adc_channel = adc_channel

    def __call__(self) -> adcs._I2C_ADC:
        return self.adc_driver(get_scl_pin(), get_sda_pin(), self.i2c_address, self.adc_channel)

    def __repr__(self) -> str:
        return f"ADCCurrier(adc_driver={self.adc_driver.__name__}, i2c_address={hex(self.i2c_address)}, adc_channel={self.adc_channel})"


_ADC_DRIVERS: dict[str, type[adcs._I2C_ADC]] = {
    "ads1115": adcs.ADS1115_ADC,
    "ads1114": adcs.ADS1114_ADC,
    "pico": adcs.Pico_ADC,
}


def _build_adc_currier_from_cfg(entry: dict[str, Any], context_key: str) -> ADCCurrier:
    try:
        driver_key = str(entry["driver"]).lower()
        driver = _ADC_DRIVERS[driver_key]
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


@cache
def _load_adc_cfg() -> dict[str, Any]:
    return get_layered_mod_config("adc")


@cache
def get_adc_curriers() -> dict[str, ADCCurrier]:
    cfg = _load_adc_cfg()
    out: dict[str, ADCCurrier] = {}
    for key in ("pd1", "pd2", "aux", "version"):
        if key in cfg:
            out[key] = _build_adc_currier_from_cfg(cfg[key], key)
        else:
            raise exc.HardwareNotFoundError(
                f"Missing adc configuration for '{key}'. Ensure hardware/models/<model>/<version>/adc.yaml or overlays provide it."
            )
    return out


# DACS


@cache
def _load_dac_cfg() -> dict[str, Any]:
    return get_layered_mod_config("dac")


@cache
def get_dac_address() -> int:
    return int(_load_dac_cfg()["address"])


__all__ = [
    "get_layered_mod_config",
    "determine_gpiochip",
    "get_pwm_controller",
    "get_heater_pwm_channel",
    "get_pwm_to_pin_map",
    "get_sda_pin",
    "get_scl_pin",
    "get_pcb_led_pin",
    "get_pcb_button_pin",
    "get_hall_sensor_pin",
    "get_temp_address",
    "get_adc_curriers",
    "get_dac_address",
    "ADCCurrier",
    "is_i2c_device_present",
    "is_DAC_present",
    "is_ADC_present",
    "is_heating_pcb_present",
    "is_HAT_present",
    "round_to_precision",
    "voltage_in_aux",
]


_DEPRECATED_EXPORTS: dict[str, Callable[[], Any]] = {
    "GPIOCHIP": determine_gpiochip,
    "PWM_CONTROLLER": get_pwm_controller,
    "HEATER_PWM_TO_PIN": get_heater_pwm_channel,
    "PWM_TO_PIN": get_pwm_to_pin_map,
    "SDA": get_sda_pin,
    "SCL": get_scl_pin,
    "PCB_LED_PIN": get_pcb_led_pin,
    "PCB_BUTTON_PIN": get_pcb_button_pin,
    "HALL_SENSOR_PIN": get_hall_sensor_pin,
    "TEMP_ADDRESS": get_temp_address,
    "TEMP": get_temp_address,
    "ADCs": get_adc_curriers,
    "DAC_ADDRESS": get_dac_address,
    "DAC": get_dac_address,
}


def __getattr__(name: str) -> Any:
    try:
        factory = _DEPRECATED_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'pioreactor.hardware' has no attribute {name!r}") from exc

    replacement = factory.__name__
    warnings.warn(
        f"`hardware.{name}` is deprecated; call `hardware.{replacement}()` instead. `hardware.{name}` will be removed in a future version.",
        DeprecationWarning,
        stacklevel=2,
    )
    value = factory()
    setattr(sys.modules[__name__], name, value)
    return value


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
    return is_i2c_device_present(get_dac_address())


def is_ADC_present(*args: int) -> bool:
    if args:
        to_check = set(args)
    else:
        to_check = {adc.i2c_address for adc in get_adc_curriers().values()}
    return all(is_i2c_device_present(c) for c in to_check)


def is_heating_pcb_present() -> bool:
    return is_i2c_device_present(get_temp_address())


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
        aux_adc = get_adc_curriers()["aux"]
    else:
        from pioreactor.utils.mock import Mock_ADC  # type: ignore

        aux_adc = ADCCurrier(Mock_ADC, 0x00, 0)

    adc = aux_adc()
    slope = 0.134  # from schematic

    return round_to_precision(
        adc.from_raw_to_voltage(adc.read_from_channel()) / slope,
        p=precision,
    )
