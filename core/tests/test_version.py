# -*- coding: utf-8 -*-
from pioreactor.version import __version__


def test_no_zero_padding() -> None:
    parts = __version__.split(".")
    for p in parts:
        assert not p.startswith("0")
