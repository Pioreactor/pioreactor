# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.metadata as entry_point
import sys
from pathlib import Path

from pioreactor.whoami import is_testing_env


def discover_plugins_in_local_folder() -> list[Path]:
    if is_testing_env():
        MODULE_DIR = Path("plugins_dev")
    else:
        MODULE_DIR = Path("/home/pioreactor/.pioreactor/plugins")

    sys.path.append(str(MODULE_DIR))

    # Get the stem names (file name, without directory and '.py') of any
    # python files in your directory, load each module by name and run
    # the required function.
    return sorted(MODULE_DIR.glob("*.py"))


def discover_plugins_in_entry_points() -> list[entry_point.EntryPoint]:
    eps = entry_point.entry_points()
    return eps.get("pioreactor.plugins", [])
