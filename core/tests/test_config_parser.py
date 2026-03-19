# -*- coding: utf-8 -*-
import configparser

import pytest
from pioreactor.config import ConfigParserMod


@pytest.mark.parametrize("getter_name", ["getint", "getfloat", "getboolean"])
@pytest.mark.parametrize(
    ("section", "option", "expected_exception"),
    [
        ("present", "missing", configparser.NoOptionError),
        ("missing", "value", configparser.NoSectionError),
    ],
)
def test_typed_getters_raise_for_missing_config_values(
    getter_name: str, section: str, option: str, expected_exception: type[Exception]
) -> None:
    config = ConfigParserMod()
    config.read_string("[present]\nvalue=1\n")

    getter = getattr(config, getter_name)

    with pytest.raises(expected_exception):
        getter(section, option)


@pytest.mark.parametrize("getter_name", ["getint", "getfloat", "getboolean"])
@pytest.mark.parametrize(("section", "option"), [("present", "missing"), ("missing", "value")])
def test_typed_getters_return_explicit_fallback_for_missing_config_values(
    getter_name: str, section: str, option: str
) -> None:
    config = ConfigParserMod()
    config.read_string("[present]\nvalue=1\n")

    getter = getattr(config, getter_name)

    assert getter(section, option, fallback="fallback-value") == "fallback-value"
