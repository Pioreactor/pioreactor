# -*- coding: utf-8 -*-
import re

from pioreactor.version import __version__


def test_no_zero_padding() -> None:
    parts = re.match(r"^(\d+\.\d+\.\d+)", __version__)
    assert parts is not None

    release_parts = parts.group(1).split(".")
    for p in release_parts:
        assert p == "0" or not p.startswith("0")
