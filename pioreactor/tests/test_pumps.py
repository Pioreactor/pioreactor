# -*- coding: utf-8 -*-
import pytest, json

from pioreactor.actions.add_media import add_media
from pioreactor.actions.add_alt_media import add_alt_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.utils import local_persistant_storage

unit = get_unit_name()
exp = get_latest_experiment_name()


def setup_function():
    with local_persistant_storage("pump_calibration") as cache:
        cache["media_ml_calibration"] = json.dumps({"duration_": 1.0})
        cache["alt_media_ml_calibration"] = json.dumps({"duration_": 1.0})
        cache["waste_ml_calibration"] = json.dumps({"duration_": 1.0})


def test_pump_io():
    add_media(ml=0.1, unit=unit, experiment=exp)
    add_alt_media(ml=0.1, unit=unit, experiment=exp)
    remove_waste(ml=0.1, unit=unit, experiment=exp)

    add_media(duration=0.1, unit=unit, experiment=exp)
    add_alt_media(duration=0.1, unit=unit, experiment=exp)
    remove_waste(duration=0.1, unit=unit, experiment=exp)


def test_pump_io_doesnt_allow_negative():
    with pytest.raises(AssertionError):
        add_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(ml=-1, unit=unit, experiment=exp)

    with pytest.raises(AssertionError):
        add_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(duration=-1, unit=unit, experiment=exp)


def test_pump_io_cant_set_both_duration_and_ml():
    with pytest.raises(AssertionError):
        add_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(ml=1, duration=1, unit=unit, experiment=exp)
