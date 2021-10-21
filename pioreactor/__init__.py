# -*- coding: utf-8 -*-
from __future__ import annotations
import glob, importlib, os, pathlib, sys

try:
    from importlib.metadata import entry_points, metadata
except ImportError:  # TODO: this is available in 3.8+
    from importlib_metadata import entry_points, metadata

from collections import namedtuple

from pioreactor.version import __version__  # noqa: F401


def __getattr__(attr):
    if attr == "plugins":
        return get_plugins()
    else:
        raise AttributeError


Plugin = namedtuple("Plugin", ["module", "description", "version", "homepage", "source"])


def get_plugins() -> dict[str, Plugin]:
    """
    This function is really time consuming...
    """

    # get entry point plugins
    # Users can use Python's entry point system to create rich plugins, see
    # example here: https://github.com/Pioreactor/pioreactor-air-bubbler
    eps = entry_points()
    pioreactor_plugins = eps.get("pioreactor.plugins", [])
    plugins = {}
    for plugin in pioreactor_plugins:
        try:
            md = metadata(plugin.name)
            plugins[md["Name"]] = Plugin(
                plugin.load(),
                md["Summary"],
                md["Version"],
                md["Home-page"],
                "entry_points",
            )
        except Exception as e:
            print(f"{plugin.name} plugin load error: {e}")

    # get file-based plugins.
    # Users can put .py files into the MODULE_DIR folder below.
    # The below code will load it into Python, and treat it like any other plugin.
    # The authors can add metadata to their file with the following variables at the
    # highest level in the file:
    # __name__
    # __summary__
    # __version__
    # __homepage__
    BLANK = "UNKNOWN"

    # The directory containing your modules needs to be on the search path.
    MODULE_DIR = "/home/pi/.pioreactor/plugins"
    sys.path.append(MODULE_DIR)

    # Get the stem names (file name, without directory and '.py') of any
    # python files in your directory, load each module by name and run
    # the required function.
    py_files = glob.glob(os.path.join(MODULE_DIR, "*.py"))

    for py_file in py_files:
        module_name = pathlib.Path(py_file).stem
        module = importlib.import_module(module_name)
        plugins[getattr(module, "__name__", module_name)] = Plugin(
            module,
            getattr(module, "__summary__", BLANK),
            getattr(module, "__version__", BLANK),
            getattr(module, "__homepage__", BLANK),
            "plugins_folder",
        )

    return plugins
