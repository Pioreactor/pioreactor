# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import UTC
from math import sqrt

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


def test_identity() -> None:
    assert parse_profile_expression("test") == "test"
    assert parse_profile_expression("test_test") == "test_test"
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("True") is True


def test_simple_bool() -> None:
    assert parse_profile_expression_to_bool("True and True")
    assert not parse_profile_expression_to_bool("True and False")
    assert parse_profile_expression_to_bool("True or False")
    assert parse_profile_expression_to_bool("True and (True or False)")
    assert parse_profile_expression_to_bool("(False or True) or False")
    assert parse_profile_expression_to_bool("not False")
    assert not parse_profile_expression_to_bool("not (True)")


def test_syntax_errors_and_typos() -> None:
    with pytest.raises(SyntaxError):
        assert parse_profile_expression_to_bool("(False or True) or False)") is None  # unbalanced paren

    with pytest.raises(LexError):
        assert parse_profile_expression_to_bool("test.test > 1")  # test.test is too few for mqtt fetches


def test_simple_float_comparison() -> None:
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


def test_mqtt_fetches() -> None:
    # complex

    experiment = "_testing_experiment"

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od1",
        encode(
            structs.RawODReading(
                timestamp=datetime.now(UTC),
                angle="90",
                od=1.2,
                channel="2",
                ir_led_intensity=90,
            )
        ),
        retain=True,
    )

    assert parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od > 1.0")
    assert parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od < 2.0")
    assert not parse_profile_expression_to_bool(f"{unit}:od_reading:od1.od > 2.0")

    # ints
    publish(f"pioreactor/{unit}/{experiment}/test_job/int", 101, retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:int == 101")
    assert parse_profile_expression_to_bool(f"{unit}:test_job:int > 100")

    # floats
    publish(f"pioreactor/{unit}/{experiment}/test_job/float", 101.5, retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:float > 100.0")
    assert parse_profile_expression_to_bool(f"{unit}:test_job:float == 101.5")

    # str
    publish(f"pioreactor/{unit}/{experiment}/test_job/string", "hi", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:string == hi")
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:string == test")

    # states as str
    publish(f"pioreactor/{unit}/{experiment}/test_job/$state", "ready", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:$state == ready")
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:$state == sleeping")

    # bool
    publish(f"pioreactor/{unit}/{experiment}/test_job/bool_true", "true", retain=True)
    publish(f"pioreactor/{unit}/{experiment}/test_job/bool_false", "false", retain=True)
    assert parse_profile_expression_to_bool(f"{unit}:test_job:bool_true")
    assert parse_profile_expression_to_bool(f"not {unit}:test_job:bool_false")
    assert parse_profile_expression_to_bool(f"{unit}:test_job:bool_false or {unit}:test_job:bool_true")


def test_mqtt_fetches_with_env() -> None:
    experiment = "_testing_experiment"

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od1",
        encode(
            structs.RawODReading(
                timestamp=datetime.now(UTC),
                angle="90",
                od=1.2,
                channel="2",
                ir_led_intensity=80,
            )
        ),
        retain=True,
    )

    assert parse_profile_expression_to_bool("::od_reading:od1.od > 1.0", env={"unit": unit})
    assert parse_profile_expression_to_bool("::od_reading:od1.od < 2.0", env={"unit": unit})
    assert not parse_profile_expression_to_bool("::od_reading:od1.od > 2.0", env={"unit": unit})

    with pytest.raises(KeyError):
        assert not parse_profile_expression_to_bool("::od_reading:od1.od > 2.0")


def test_mqtt_timeout() -> None:
    with pytest.raises(ValueError):
        assert parse_profile_expression_to_bool(f"{unit}:test_job:does_not_exist or True")


def test_calculator() -> None:
    assert parse_profile_expression("True + True") == 2.0
    assert parse_profile_expression("1 + 1") == 2
    assert parse_profile_expression("1.0 - 1.0") == 0.0
    assert parse_profile_expression("-1.5") == -1.5
    assert parse_profile_expression("-1.5 * 2.0") == -3.0
    assert parse_profile_expression("-1.5 * -2.0") == 3.0
    assert parse_profile_expression("-1.5 / -2.0") == 0.75
    assert parse_profile_expression("4 ** 0.5") == sqrt(4)
    assert parse_profile_expression("1 ** 100.0") == 1.0
    assert parse_profile_expression("2.5 ** 0.5") == sqrt(2.5)
    assert parse_profile_expression("2 ** (2 + 2)") == 2 ** (2 + 2)
    assert 0 <= parse_profile_expression("random()") <= 1.0
    assert 25 <= parse_profile_expression("25 + (25 * random())") <= 50

    with pytest.raises(ZeroDivisionError):
        assert parse_profile_expression("-1.5 / 0") == 0.75


def test_env_and_functions() -> None:
    parse_profile_expression("unit()", env={"unit": "test"}) == "test"
    assert parse_profile_expression("unit() == test", env={"unit": "test"})

    assert not parse_profile_expression("unit() == test", env={"unit": "not_test"})

    parse_profile_expression("experiment()", env={"experiment": "exp001"}) == "exp001"

    publish(
        "pioreactor/unit1/_testing_experiment/stirring/target_rpm",
        100,
        retain=True,
    )
    parse_profile_expression(
        "unit():job_name():target_rpm", env={"unit": "unit1", "job_name": "stirring"}
    ) == 100

    with pytest.raises(KeyError):
        parse_profile_expression("unit()", env={})


def test_env() -> None:
    assert parse_profile_expression("rpm + 5.0", env={"rpm": 100}) == 105.0
    assert parse_profile_expression("rpm_start * other", env={"rpm_start": 10, "other": 6.6}) == 10 * 6.6
    assert parse_profile_expression("b", env={"b": True})


def test_mqtt_fetches_with_calculations() -> None:
    experiment = "_testing_experiment"
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od1",
        encode(
            structs.RawODReading(
                timestamp=datetime.now(UTC),
                angle="90",
                od=1.2,
                channel="2",
                ir_led_intensity=80,
            )
        ),
        retain=True,
    )

    assert parse_profile_expression(f"2 * {unit}:od_reading:od1.od ") == 2 * 1.2
    assert (
        parse_profile_expression(
            f"{unit}:od_reading:od1.od + {unit}:od_reading:od1.od + {unit}:od_reading:od1.od",
        )
        == 3 * 1.2
    )
    assert parse_profile_expression(f"({unit}:od_reading:od1.od + {unit}:od_reading:od1.od) > 2.0 ") is True
