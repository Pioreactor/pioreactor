# -*- coding: utf-8 -*-
import ast
import importlib.metadata as entry_point
import os
import sys
import zipfile
from email.parser import HeaderParser
from pathlib import Path

from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.whoami import is_testing_env


def discover_plugins_in_local_folder() -> list[Path]:
    if is_testing_env():
        if "PLUGINS_DEV" not in os.environ:
            return []

        MODULE_DIR = Path(os.environ["PLUGINS_DEV"])
    else:
        MODULE_DIR = get_dot_pioreactor_path() / "plugins"

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


def discover_plugins_in_entry_points() -> list[entry_point.EntryPoint]:
    return list(entry_point.entry_points(group="pioreactor.plugins"))


# The display_name helpers below return the name the Plugins list shows, for use in log messages.


def get_package_plugin_display_name(plugin_name: str) -> str:
    """Installed packages are listed by their distribution metadata Name."""
    try:
        return entry_point.metadata(plugin_name)["Name"] or plugin_name
    except entry_point.PackageNotFoundError:
        return plugin_name


def get_python_plugin_file_display_name(py_file: Path) -> str:
    """.py drop-ins are listed by their __plugin_name__, else their file stem. Read without importing the file."""
    try:
        tree = ast.parse(py_file.read_text())
    except (OSError, SyntaxError, UnicodeDecodeError):
        return py_file.stem

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if (
            any(isinstance(target, ast.Name) and target.id == "__plugin_name__" for target in targets)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            return value.value
    return py_file.stem


def get_wheel_plugin_display_name(wheel: Path) -> str:
    """A wheel installs a package listed by the Name in its METADATA."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if member.count("/") == 1 and member.endswith(".dist-info/METADATA"):
                    name = HeaderParser().parsestr(archive.read(member).decode())["Name"]
                    if name:
                        return name
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError):
        pass
    return wheel.name.split("-")[0].replace("_", "-")


def get_plugin_display_name(plugin_name: str) -> str:
    """A name passed to `pio plugins uninstall` is either a .py drop-in's stem or a package name."""
    for py_file in discover_plugins_in_local_folder():
        if py_file.stem == plugin_name:
            return get_python_plugin_file_display_name(py_file)
    return get_package_plugin_display_name(plugin_name)


def get_plugin_artifact_display_name(artifact: Path) -> str:
    if artifact.suffix == ".whl":
        return get_wheel_plugin_display_name(artifact)
    return get_python_plugin_file_display_name(artifact)
