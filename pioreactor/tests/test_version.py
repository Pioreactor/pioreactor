# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.version import __version__


def test_no_zero_padding():
    parts = __version__.split(".")
    for p in parts:
        assert not p.startswith("0")
