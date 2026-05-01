# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import importlib.metadata as entry_point


def _is_testing_env() -> bool:
    return ("pytest" in sys.modules) or (os.environ.get("TESTING", "") == "1")


def discover_plugins_in_local_folder() -> list[Path]:
    if _is_testing_env():
        if "PLUGINS_DEV" not in os.environ:
            return []

        MODULE_DIR = Path(os.environ["PLUGINS_DEV"])
    else:
        MODULE_DIR = Path("/home/pioreactor/.pioreactor/plugins")

    # Python searches in the directories in sys.path for module resolution.
    # the first element is "", which represents the local dir
    # later elements are where stdlib are found, third party libs are found, etc.
    # we inject our plugins in between local and stdlib. This solves issue #447.
    # however, users can break things if the name the file something stupid like os.py
    module_dir = str(MODULE_DIR)
    if module_dir not in sys.path:
        sys.path.insert(1, module_dir)

    # Get the stem names (file name, without directory and '.py') of any
    # python files in your directory, load each module by name and run
    # the required function.

    return sorted(MODULE_DIR.glob("*.py"))


def discover_plugins_in_entry_points() -> list["entry_point.EntryPoint"]:
    import importlib.metadata as entry_point

    eps = entry_point.entry_points()
    return list(eps.select(group="pioreactor.plugins"))
