# -*- coding: utf-8 -*-
# test automation_yamls
from __future__ import annotations

from yaml import load  # type: ignore
from yaml import Loader  # type: ignore

from pioreactor.automations import *  # noqa: F403, F401
from pioreactor.background_jobs.dosing_control import DosingController
from pioreactor.background_jobs.led_automation import available_led_automations
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.mureq import get


def get_specific_yaml(path):
    data = get(f"https://raw.githubusercontent.com/Pioreactor/pioreactorui/master/{path}")
    return load(data.content, Loader=Loader)


def test_automations_and_their_yamls_have_the_same_data():
    try:
        for automation_name, klass in available_led_automations.items():
            if automation_name.startswith("_test"):
                continue

            data = get_specific_yaml(f"contrib/automations/led/{automation_name}.yaml")
            assert data["automation_name"] == automation_name, automation_name

            # check yaml -> settings
            for field in data["fields"]:
                key = field["key"]
                assert field["unit"] == klass.published_settings[key]["unit"]

            # check settings -> yaml
            for setting in klass.published_settings:
                assert any([f["key"] == setting for f in data["fields"]])

        for automation_name, klass in DosingController.available_automations.items():
            if automation_name.startswith("_test"):
                continue

            data = get_specific_yaml(f"contrib/automations/dosing/{automation_name}.yaml")
            assert data["automation_name"] == automation_name, automation_name

            for field in data["fields"]:
                key = field["key"]
                assert field["unit"] == klass.published_settings[key]["unit"]

            for setting in klass.published_settings:
                assert any([f["key"] == setting for f in data["fields"]])

        for automation_name, klass in TemperatureController.available_automations.items():
            if automation_name.startswith("_test"):
                continue

            data = get_specific_yaml(f"contrib/automations/temperature/{automation_name}.yaml")
            assert data["automation_name"] == automation_name, automation_name

            for field in data["fields"]:
                key = field["key"]
                assert field["unit"] == klass.published_settings[key]["unit"]

            for setting in klass.published_settings:
                assert any([f["key"] == setting for f in data["fields"]])
    except Exception as e:
        print(automation_name, klass)
        raise e
