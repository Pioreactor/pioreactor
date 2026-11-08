# -*- coding: utf-8 -*-
import configparser
from string import ascii_letters
from string import digits
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from pioreactor.config import ConfigParserMod
from pioreactor.config import replace_or_append_config_entry


@settings(max_examples=100)
@given(
    entries=st.dictionaries(
        st.text(ascii_letters + digits + "_", min_size=1, max_size=12).map(lambda key: "setting_" + key),
        st.text(ascii_letters + digits + "_./:-", min_size=1, max_size=20),
        min_size=1,
        max_size=6,
    ),
    value=st.text(ascii_letters + digits + "_./:-", min_size=1, max_size=20),
    scenario=st.sampled_from(["existing", "missing_key", "missing_section"]),
    target_first=st.booleans(),
    newline=st.sampled_from(["\n", "\r\n"]),
    trailing_newline=st.booleans(),
)
def test_property_config_edit_changes_only_requested_value_and_is_idempotent(
    entries: dict[str, str],
    value: str,
    scenario: str,
    target_first: bool,
    newline: str,
    trailing_newline: bool,
) -> None:
    parameter = next(iter(entries)) if scenario == "existing" else "missing"
    other = ["[other]", "# Unrelated section", f"{parameter}=untouched"]
    target = ["[target]", "; Target settings"] + [f"{key}={value}" for key, value in entries.items()]
    sections = (
        (target + other if target_first else other + target) if scenario != "missing_section" else other
    )
    source = newline.join(sections) + (newline if trailing_newline else "")
    before = ConfigParserMod()
    before.read_string(source)
    expected = {section: dict(before[section]) for section in before.sections()}
    expected["target"] = {**expected.get("target", {}), parameter: value}

    updated = replace_or_append_config_entry(source, "target", parameter, value)
    after = ConfigParserMod()
    after.read_string(updated)

    assert {section: dict(after[section]) for section in after.sections()} == expected
    assert replace_or_append_config_entry(updated, "target", parameter, value) == updated


@settings(max_examples=100)
@given(
    indent=st.sampled_from(["", " ", "  ", "\t"]),
    delimiter=st.sampled_from(["=", " =", ":", " :"]),
    newline=st.sampled_from(["\n", "\r\n"]),
    value=st.text(ascii_letters + digits + "_./:-", min_size=1, max_size=20),
    comment=st.text(ascii_letters + digits + " []:=#;\t", max_size=40),
)
def test_property_config_edit_preserves_comments_and_layout(
    indent: str, delimiter: str, newline: str, value: str, comment: str
) -> None:
    prefix = [f"# {comment}", "[before]", "setting=keep_before", "", "[target]", f"; {comment}"]
    suffix = ["", "# Keep this comment", "[after]", "setting:keep_after"]
    source = newline.join(prefix + [f"{indent}setting{delimiter}old"] + suffix) + newline

    updated = replace_or_append_config_entry(source, "target", "setting", value)

    expected = newline.join(prefix + [f"{indent}setting{delimiter}{value}"] + suffix) + newline
    assert updated == expected


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


@pytest.mark.parametrize("getter_name", ["getint", "getfloat", "getboolean"])
def test_typed_getters_with_fallback_do_not_log_missing_values(getter_name: str) -> None:
    config = ConfigParserMod()
    config.read_string("[present]\nvalue=1\n")

    with patch("pioreactor.logging.create_logger") as create_logger:
        assert getattr(config, getter_name)("present", "missing", fallback=0) == 0

    create_logger.assert_not_called()


@pytest.mark.parametrize(
    ("fallback", "expected"), [("false", False), ("0", False), ("True", True), ("1", True)]
)
def test_getboolean_parses_boolean_string_fallbacks(fallback: str, expected: bool) -> None:
    config = ConfigParserMod()
    config.read_string("[present]\nvalue=1\n")

    assert config.getboolean("present", "missing", fallback=fallback) is expected
    assert config.getboolean("missing", "value", fallback=fallback) is expected
