# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from msgspec.json import encode

from pioreactor import structs
from pioreactor.experiment_profiles.parser import parse_profile_expression
from pioreactor.experiment_profiles.parser import parse_profile_expression_to_bool
from pioreactor.experiment_profiles.sly.lex import LexError
from pioreactor.pubsub import publish
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name

unit = get_unit_name()
exp = get_assigned_experiment_name(unit)


def test_identity():
    assert parse_profile_expression("test") == "test"
    assert parse_profile_expression("test_test") == "test_test"
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("True") is True


def test_simple_bool():
    assert parse_profile_expression_to_bool("True and True")
    assert not parse_profile_expression_to_bool("True and False")
    assert parse_profile_expression_to_bool("True or False")
    assert parse_profile_expression_to_bool("True and (True or False)")
    assert parse_profile_expression_to_bool("(False or True) or False")
    assert parse_profile_expression_to_bool("not False")
    assert not parse_profile_expression_to_bool("not (True)")


def test_syntax_errors_and_typos():
    with pytest.raises(SyntaxError):
        assert parse_profile_expression_to_bool("(False or True) or False)") is None  # unbalanced paren

    with pytest.raises(LexError):
        assert parse_profile_expression_to_bool("test.test > 1")  # test.test is too few for mqtt fetches


def test_simple_float_comparison():
    assert parse_profile_expression_to_bool("1 > 0")
    assert not parse_profile_expression_to_bool("1 < 0")
    assert parse_profile_expression_to_bool("1.1 > -1.1")
    assert not parse_profile_expression_to_bool("1.1 > 1.1")
    assert parse_profile_expression_to_bool("-1.1 > -2")
    assert parse_profile_expression_to_bool("(0 > 1) or (1 > 0)")
    assert parse_profile_expression_to_bool("1.0 == 1.0")
    assert parse_profile_expression_to_bool("1.0 >= 1.0")
    assert parse_profile_expression_to_bool("2.5 >= 1.0")
    assert not parse_profile_expression_to_bool("2.5 <= 1.0")
    assert parse_profile_expression_to_bool("-1 <= 1.0")


def test_mqtt_fetches():
    # complex

    experiment = "test_mqtt_fetches"

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od1",
        encode(structs.ODReading(timestamp="2021-01-01", angle="90", od=1.2, channel="2")),
        retain=True,
    )

    assert parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od > 1.0", experiment=experiment)
    assert parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od < 2.0", experiment=experiment)
    assert not parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od > 2.0", experiment=experiment)

    # ints
    publish(f"pioreactor/{unit}/{experiment}/test_job/int", 101, retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:int == 101", experiment=experiment)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:int > 100", experiment=experiment)

    # floats
    publish(f"pioreactor/{unit}/{experiment}/test_job/float", 101.5, retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:float > 100.0", experiment=experiment)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:float == 101.5", experiment=experiment)

    # str
    publish(f"pioreactor/{unit}/{experiment}/test_job/string", "hi", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:string == hi", experiment=experiment)
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:string == test", experiment=experiment)

    # states as str
    publish(f"pioreactor/{unit}/{experiment}/test_job/$state", "ready", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:$state == ready", experiment=experiment)
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:$state == sleeping", experiment=experiment)

    # bool
    publish(f"pioreactor/{unit}/{experiment}/test_job/bool_true", "true", retain=True)
    publish(f"pioreactor/{unit}/{experiment}/test_job/bool_false", "false", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:bool_true", experiment=experiment)
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:bool_false", experiment=experiment)
    assert parse_profile_expression_to_bool(
        f"{unit}:test_job:bool_false or {unit}:test_job:bool_true", experiment=experiment
    )


def test_mqtt_timeout():
    with pytest.raises(ValueError):
        assert parse_profile_expression_to_bool(f"{unit}:test_job:does_not_exist or True", experiment="test")


def test_calculator():
    assert parse_profile_expression("True + True") == 2.0
    assert parse_profile_expression("1 + 1") == 2
    assert parse_profile_expression("1.0 - 1.0") == 0.0
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("-1.5 * 2.0") == -3.0
    assert parse_profile_expression("-1.5 * -2.0") == 3.0
    assert parse_profile_expression("-1.5 / -2.0") == 0.75

    with pytest.raises(ZeroDivisionError):
        assert parse_profile_expression("-1.5 / 0") == 0.75


def test_mqtt_fetches_with_calculations():
    experiment = "test_mqtt_fetches_with_calculations"
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od1",
        encode(structs.ODReading(timestamp="2021-01-01", angle="90", od=1.2, channel="2")),
        retain=True,
    )

    assert parse_profile_expression(f"2 * {unit}:od_reading:od1.od ", experiment=experiment) == 2 * 1.2
    assert (
        parse_profile_expression(
            f"{unit}:od_reading:od1.od + {unit}:od_reading:od1.od + {unit}:od_reading:od1.od",
            experiment=experiment,
        )
        == 3 * 1.2
    )
    assert (
        parse_profile_expression(
            f"({unit}:od_reading:od1.od + {unit}:od_reading:od1.od) > 2.0 ", experiment=experiment
        )
        is True
    )
