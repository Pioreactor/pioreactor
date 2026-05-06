# -*- coding: utf-8 -*-
import builtins
import re
from typing import Any

from pioreactor.version import __version__
from pioreactor.version import get_rpi_machine


def test_no_zero_padding() -> None:
    parts = re.match(r"^(\d+\.\d+\.\d+)", __version__)
    assert parts is not None

    release_parts = parts.group(1).split(".")
    for p in release_parts:
        assert p == "0" or not p.startswith("0")


def test_get_rpi_machine_is_blank_when_device_tree_model_is_missing(monkeypatch) -> None:
    real_open = builtins.open

    def fake_open(file: str, *args: Any, **kwargs: Any) -> Any:
        if file == "/proc/device-tree/model":
            raise FileNotFoundError
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    assert get_rpi_machine() == ""
