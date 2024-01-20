# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from msgspec.json import encode

from pioreactor import structs
from pioreactor.experiment_profiles.boolean_parser import parse_profile_if_directive_to_bool
from pioreactor.experiment_profiles.sly.lex import LexError
from pioreactor.pubsub import publish
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name

unit = get_unit_name()
exp = get_latest_experiment_name()


def test_simple_bool():
    assert parse_profile_if_directive_to_bool("True and True")
    assert not parse_profile_if_directive_to_bool("True and False")
    assert parse_profile_if_directive_to_bool("True or False")
    assert parse_profile_if_directive_to_bool("True and (True or False)")
    assert parse_profile_if_directive_to_bool("(False or True) or False")
    assert parse_profile_if_directive_to_bool("not False")
    assert not parse_profile_if_directive_to_bool("not (True)")


def test_syntax_errors_and_typos():
    assert parse_profile_if_directive_to_bool("(False or True) or False)") is None  # unbalanced paren

    with pytest.raises(LexError):
        assert parse_profile_if_directive_to_bool("test.test > 1")  # test.test is too few for mqtt fetches


def test_simple_float():
    assert parse_profile_if_directive_to_bool("1 > 0")
    assert not parse_profile_if_directive_to_bool("1 < 0")
    assert parse_profile_if_directive_to_bool("1.1 > -1.1")
    assert not parse_profile_if_directive_to_bool("1.1 > 1.1")
    assert parse_profile_if_directive_to_bool("-1.1 > -2")
    assert parse_profile_if_directive_to_bool("(0 > 1) or (1 > 0)")
    assert parse_profile_if_directive_to_bool("1.0 == 1.0")
    assert parse_profile_if_directive_to_bool("1.0 >= 1.0")
    assert parse_profile_if_directive_to_bool("2.5 >= 1.0")
    assert not parse_profile_if_directive_to_bool("2.5 <= 1.0")
    assert parse_profile_if_directive_to_bool("-1 <= 1.0")


def test_mqtt_fetches():
    # complex
    publish(
        f"pioreactor/{unit}/{exp}/od_reading/od1",
        encode(structs.ODReading(timestamp="2021-01-01", angle="90", od=1.2, channel="2")),
        retain=True,
    )

    assert parse_profile_if_directive_to_bool(f"{unit}.od_reading.od1.od > 1.0")
    assert parse_profile_if_directive_to_bool(f"{unit}.od_reading.od1.od < 2.0")
    assert not parse_profile_if_directive_to_bool(f"{unit}.od_reading.od1.od > 2.0")

    # floats
    publish(f"pioreactor/{unit}/{exp}/test_job/float", 101.5, retain=True)
    assert parse_profile_if_directive_to_bool(f"{unit}.test_job.float > 100.0")
    assert parse_profile_if_directive_to_bool(f"{unit}.test_job.float == 101.5")

    # str
    publish(f"pioreactor/{unit}/{exp}/test_job/string", "hi", retain=True)
    assert parse_profile_if_directive_to_bool(f"{unit}.test_job.string == hi")
    assert parse_profile_if_directive_to_bool(f"not {unit}.test_job.string == test")

    # bool
    publish(f"pioreactor/{unit}/{exp}/test_job/bool_true", "true", retain=True)
    publish(f"pioreactor/{unit}/{exp}/test_job/bool_false", "false", retain=True)
    assert parse_profile_if_directive_to_bool(f"{unit}.test_job.bool_true")
    assert parse_profile_if_directive_to_bool(f"not {unit}.test_job.bool_false")
    assert parse_profile_if_directive_to_bool(f"{unit}.test_job.bool_false or {unit}.test_job.bool_true")


def test_mqtt_timeout():
    with pytest.raises(ValueError):
        assert parse_profile_if_directive_to_bool(f"{unit}.test_job.does_not_exist or True")
