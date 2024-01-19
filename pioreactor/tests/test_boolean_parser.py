# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from pioreactor.experiment_profiles.boolean_parser import parse_profile_if_directive_to_bool


def test_simple_bool():
    assert parse_profile_if_directive_to_bool("True and True")
    assert not parse_profile_if_directive_to_bool("True and False")
    assert parse_profile_if_directive_to_bool("True or False")
    assert parse_profile_if_directive_to_bool("True and (True or False)")
    assert parse_profile_if_directive_to_bool("(False or True) or False")
    assert parse_profile_if_directive_to_bool("not False")
    assert not parse_profile_if_directive_to_bool("not (True)")


def test_typos():
    assert parse_profile_if_directive_to_bool("(False or True) or False)") is None  # unbalanced paren

    with pytest.raises(SyntaxError):
        assert parse_profile_if_directive_to_bool("true")  # true not defined
    with pytest.raises(SyntaxError):
        assert parse_profile_if_directive_to_bool("test")  # test not defined


def test_simple_float():
    assert parse_profile_if_directive_to_bool("1 > 0")
    assert not parse_profile_if_directive_to_bool("1 < 0")
    assert parse_profile_if_directive_to_bool("1.1 > -1.1")
    assert not parse_profile_if_directive_to_bool("1.1 > 1.1")
    assert parse_profile_if_directive_to_bool("-1.1 > -2")
    assert parse_profile_if_directive_to_bool("(0 > 1) or (1 > 0)")


def test_mqtt_fetches():
    # I hate all these

    # doesn't know how to decode
    assert parse_profile_if_directive_to_bool("_testing_unit.od_reading.od1.od > 1.0")
    assert parse_profile_if_directive_to_bool(
        "_testing_unit.temperature_control.temperature.temperature > 1.0"
    )
