# -*- coding: utf-8 -*-
from __future__ import annotations


__version__ = "21.12.0"


def _get_hardware_version():
    return (0, 0)


hardware_version_info = _get_hardware_version()
software_version_info = tuple(int(c) for c in __version__.split(","))
