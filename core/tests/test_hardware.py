# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from pioreactor import exc
from pioreactor import hardware
from pioreactor.models import PIOREACTOR_40ml__v1_5


@pytest.mark.parametrize(
    "name",
    [
        "GPIOCHIP",
        "PWM_CONTROLLER",
        "HEATER_PWM_TO_PIN",
        "PWM_TO_PIN",
        "SDA",
        "SCL",
        "PCB_LED_PIN",
        "PCB_BUTTON_PIN",
        "HALL_SENSOR_PIN",
        "TEMP_ADDRESS",
        "TEMP",
        "ADCs",
        "DAC_ADDRESS",
        "DAC",
    ],
)
def test_legacy_hardware_constants_are_removed(name: str) -> None:
    with pytest.raises(AttributeError):
        getattr(hardware, name)


def test_hardware_getter_imports_remain_available() -> None:
    from pioreactor.hardware import get_heater_pwm_channel
    from pioreactor.hardware import get_pwm_to_pin_map
    from pioreactor.hardware import get_scl_pin
    from pioreactor.hardware import get_sda_pin
    from pioreactor.hardware import get_temp_address

    assert isinstance(get_temp_address(), int)
    assert isinstance(get_scl_pin(), int)
    assert isinstance(get_sda_pin(), int)
    assert isinstance(get_pwm_to_pin_map()[get_heater_pwm_channel()], int)


@pytest.mark.parametrize("loader", ["assigned", "explicit"])
@pytest.mark.parametrize("hat_extension", ["yaml", "yml"])
@pytest.mark.parametrize("model_extension", ["yaml", "yml"])
def test_hardware_layers_accept_both_extensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: str,
    hat_extension: str,
    model_extension: str,
) -> None:
    model = PIOREACTOR_40ml__v1_5
    monkeypatch.setattr(hardware, "get_dot_pioreactor_path", lambda: tmp_path)
    monkeypatch.setattr(hardware, "hardware_version_info", (1, 2))
    monkeypatch.setattr(hardware, "get_pioreactor_model", lambda: model)
    hat_dir = tmp_path / "hardware/hats/1.2"
    model_dir = tmp_path / "hardware/models" / model.model_name / model.model_version
    hat_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    (hat_dir / f"pwm.{hat_extension}").write_text(
        'pwm_to_pin: {"1": 17, "2": 13}\ncontroller: rpi_gpio\n', encoding="utf-8"
    )
    (model_dir / f"pwm.{model_extension}").write_text('pwm_to_pin: {"1": 22}\n', encoding="utf-8")

    if loader == "assigned":
        result = hardware.get_layered_mod_config("pwm")
    else:
        result = hardware.get_layered_mod_config_for_model("pwm", model.model_name, model.model_version)

    assert result == {"pwm_to_pin": {"1": 22, "2": 13}, "controller": "rpi_gpio"}


@pytest.mark.parametrize("yaml_content", ["pin: 17\n", ""])
def test_yaml_takes_precedence_over_yml(tmp_path: Path, yaml_content: str) -> None:
    path = tmp_path / "gpio.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    path.with_suffix(".yml").write_text("pin: 22\n", encoding="utf-8")

    assert hardware._load_yaml_if_exists(path) == ({"pin": 17} if yaml_content else {})


@pytest.mark.parametrize("extension", ["yaml", "yml"])
def test_invalid_hardware_yaml_raises(tmp_path: Path, extension: str) -> None:
    (tmp_path / f"gpio.{extension}").write_text("pin: [\n", encoding="utf-8")

    with pytest.raises(exc.HardwareError, match=f"gpio.{extension}"):
        hardware._load_yaml_if_exists(tmp_path / "gpio.yaml")


def test_missing_hardware_layer_is_empty(tmp_path: Path) -> None:
    assert hardware._load_yaml_if_exists(tmp_path / "gpio.yaml") == {}
