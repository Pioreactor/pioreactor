# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.web.utils import is_valid_unix_filename
from pioreactor.web.utils import scrub_to_valid


def test_none_input_raises() -> None:
    with pytest.raises(ValueError):
        scrub_to_valid(None)  # type: ignore[arg-type]


def test_sqlite_prefixed_input_rejected() -> None:
    with pytest.raises(ValueError):
        scrub_to_valid("sqlite_master")


@pytest.mark.parametrize(
    "dangerous,expected",
    [
        ("users; DROP TABLE users;--", "usersDROPTABLEusers"),
        ("../etc/passwd", "etcpasswd"),
        ("name\x00../../etc/passwd", "nameetcpasswd"),
    ],
)
def test_dangerous_inputs_are_scrubbed(dangerous, expected) -> None:
    assert scrub_to_valid(dangerous) == expected


@pytest.mark.parametrize(
    "name",
    [
        "file.txt",
        "data-set_01",
        "alpha beta-01.ext",
    ],
)
def test_valid_unix_filenames(name) -> None:
    assert is_valid_unix_filename(name)


@pytest.mark.parametrize(
    "name",
    [
        ".hidden",
        "-leadingdash",
        ".",
        "..",
        "dir/file",
        "dir\\file",
        "contains\x1fcontrol",
        "a" * 256,
    ],
)
def test_invalid_unix_filenames(name) -> None:
    assert not is_valid_unix_filename(name)
