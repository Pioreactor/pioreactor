# -*- coding: utf-8 -*-
# test automation_yamls
from functools import cache
from typing import Any

from pioreactor.automations import *  # noqa: F403, F401
from pioreactor.background_jobs.dosing_automation import available_dosing_automations
from pioreactor.background_jobs.dosing_automation import DosingAutomationJobContrib
from pioreactor.background_jobs.led_automation import available_led_automations
from pioreactor.background_jobs.led_automation import LEDAutomationJobContrib
from pioreactor.background_jobs.temperature_automation import available_temperature_automations
from pioreactor.background_jobs.temperature_automation import TemperatureAutomationJobContrib
from pioreactor.mureq import get
from pioreactor.mureq import head
from yaml import load  # type: ignore
from yaml import Loader  # type: ignore


CUSTOMIZER_UI_ROOT = (
    "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/"
    "pioreactor/workspace/scripts/files/pioreactor/ui"
)


def get_specific_yaml(path: str) -> dict[str, Any]:
    url = f"{CUSTOMIZER_UI_ROOT}/{path}"
    r = get(url)
    print(url)
    r.raise_for_status()
    data = r.content
    return load(data, Loader=Loader)


@cache
def get_automation_yaml_filename(type_: str, automation_name: str) -> str:
    expected_filename = f"{automation_name}.yaml"
    candidate_filenames = [expected_filename] + [f"{index:02d}_{expected_filename}" for index in range(100)]

    for filename in candidate_filenames:
        response = head(f"{CUSTOMIZER_UI_ROOT}/automations/{type_}/{filename}")
        if response.status_code == 200:
            return filename
        if response.status_code != 404:
            response.raise_for_status()

    raise FileNotFoundError(f"Unable to locate YAML for automation '{automation_name}' in '{type_}'.")


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
                        assert any([f["key"] == setting for f in data["fields"]])

    except Exception as e:
        print(automation_name, klass)
        raise e
