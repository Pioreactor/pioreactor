# -*- coding: utf-8 -*-
# test automation_yamls
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from pioreactor.automations import *  # noqa: F403, F401
from pioreactor.background_jobs.dosing_automation import available_dosing_automations
from pioreactor.background_jobs.dosing_automation import DosingAutomationJobContrib
from pioreactor.background_jobs.led_automation import available_led_automations
from pioreactor.background_jobs.led_automation import LEDAutomationJobContrib
from pioreactor.background_jobs.temperature_automation import available_temperature_automations
from pioreactor.background_jobs.temperature_automation import TemperatureAutomationJobContrib
from yaml import load  # type: ignore
from yaml import Loader  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_UI_DIR = REPO_ROOT / "packaging" / "shared-assets" / "pioreactor" / "ui"


def get_specific_yaml(path: str) -> dict[str, Any]:
    yaml_path = SHARED_UI_DIR / path
    return load(yaml_path.read_bytes(), Loader=Loader)


@cache
def get_automation_yaml_filename(type_: str, automation_name: str) -> str:
    expected_filename = f"{automation_name}.yaml"
    candidate_filenames = [expected_filename] + [f"{index:02d}_{expected_filename}" for index in range(100)]

    for filename in candidate_filenames:
        if (SHARED_UI_DIR / "automations" / type_ / filename).exists():
            return filename

    raise FileNotFoundError(f"Unable to locate YAML for automation '{automation_name}' in '{type_}'.")


@pytest.mark.slow
def test_automations_and_their_yamls_have_the_same_data() -> None:
    try:
        for type_, available_automations in [
            ("led", available_led_automations),
            ("temperature", available_temperature_automations),
            ("dosing", available_dosing_automations),
        ]:
            for automation_name, klass in available_automations.items():  # type: ignore
                if (
                    automation_name.startswith("_test")
                    or issubclass(klass, LEDAutomationJobContrib)
                    or issubclass(klass, TemperatureAutomationJobContrib)
                    or issubclass(klass, DosingAutomationJobContrib)
                ):
                    continue

                yaml_filename = get_automation_yaml_filename(type_, automation_name)
                data = get_specific_yaml(f"automations/{type_}/{yaml_filename}")
                assert data["automation_name"] == automation_name, automation_name

                # check yaml -> settings
                for field in data["fields"]:
                    key = field["key"]
                    if key == "duration":
                        continue
                    published_setting = klass.published_settings[key]
                    assert field.get("unit", "") == published_setting.get("unit", "")

                # check settings -> yaml
                for setting, metadata in klass.published_settings.items():
                    if metadata["settable"]:
                        assert any([f["key"] == setting for f in data["fields"]]), setting

    except Exception as e:
        print(automation_name, klass)
        raise e
