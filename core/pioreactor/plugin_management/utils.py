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

    # Python searches in the directories in sys.path for module resolution.
    # the first element is "", which represents the local dir
    # later elements are where stdlib are found, third party libs are found, etc.
    # we inject our plugins in between local and stdlib. This solves issue #447.
    # however, users can break things if the name the file something stupid like os.py
    sys.path.insert(1, str(MODULE_DIR))

    # Get the stem names (file name, without directory and '.py') of any
    # python files in your directory, load each module by name and run
    # the required function.
    return sorted(MODULE_DIR.glob("*.py"))


def discover_plugins_in_entry_points() -> list[entry_point.EntryPoint]:
    eps = entry_point.entry_points()
    return list(eps.select(group="pioreactor.plugins"))
