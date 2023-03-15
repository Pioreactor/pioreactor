# -*- coding: utf-8 -*-
"""
How do plugins work? There are a few patterns we use to "register" plugins with the core app.

Entry Points

   1. Plugins can use entry_points in the setup, pointing to "pioreactor.plugins"
   2. Automations are defined by a subclassing the respective XXXAutomationContrib. There is a hook in
      this parent class that will add the subclass to XXXController, hence the Controller will know about
      it and be able to run it (as the module is loaded in pioreactor.__init__.py)
   3. command-line additions, like background jobs, are found by searching the plugin's namespace for functions
      prepended with `click_`.


Adding to ~/.pioreactor/plugins

   1. Scripts placed in ~/.pioreactor/plugins are automagically loaded.
     The authors can add metadata to their file with the following variables at the
     highest level in the file:

     __plugin_name__
     __plugin_author__
     __plugin_summary__
     __plugin_version__
     __plugin_homepage__

"""
from __future__ import annotations

import glob
import importlib
import importlib.metadata as entry_point
import os
import pathlib
import sys
import typing as t

from msgspec import Struct

from .install_plugin import click_install_plugin
from .list_plugins import click_list_plugins
from .uninstall_plugin import click_uninstall_plugin
from pioreactor.whoami import is_testing_env


class Plugin(Struct):
    module: t.Any
    description: str
    version: str
    homepage: str
    author: str
    source: str


def get_plugins() -> dict[str, Plugin]:
    """
    This function is really time consuming...
    """

    # get entry point plugins
    # Users can use Python's entry point system to create rich plugins, see
    # example here: https://github.com/Pioreactor/pioreactor-air-bubbler
    eps = entry_point.entry_points()
    pioreactor_plugins: t.List[entry_point.EntryPoint] = eps.get("pioreactor.plugins", [])
    plugins: dict[str, Plugin] = {}
    for plugin in pioreactor_plugins:
        try:
            md = entry_point.metadata(plugin.name)
            plugins[md["Name"]] = Plugin(
                plugin.load(),
                md["Summary"],
                md["Version"],
                md["Home-page"],
                md["Author"],
                "entry_points",
            )
        except Exception as e:
            print(f"{plugin.name} plugin load error: {e}")

    # get file-based plugins.
    # Users can put .py files into the MODULE_DIR folder below.
    # The below code will load it into Python, and treat it like any other plugin.
    # The authors can add metadata to their file with the following variables at the
    # highest level in the file:
    # __plugin_name__
    # __plugin_author__
    # __plugin_summary__
    # __plugin_version__
    # __plugin_homepage__
    BLANK = "Unknown"

    # The directory containing your modules needs to be on the search path.
    if is_testing_env():
        MODULE_DIR = "plugins_dev"
    else:
        MODULE_DIR = "/home/pioreactor/.pioreactor/plugins"

    sys.path.append(MODULE_DIR)

    # Get the stem names (file name, without directory and '.py') of any
    # python files in your directory, load each module by name and run
    # the required function.
    py_files = sorted(glob.glob(os.path.join(MODULE_DIR, "*.py")))

    for py_file in py_files:
        try:
            module_name = pathlib.Path(py_file).stem
            module = importlib.import_module(module_name)
            plugin_name = getattr(module, "__plugin_name__", module_name)
            plugins[plugin_name] = Plugin(
                module,
                getattr(module, "__plugin_summary__", BLANK),
                getattr(module, "__plugin_version__", BLANK),
                getattr(module, "__plugin_homepage__", BLANK),
                getattr(module, "__plugin_author__", BLANK),
                "plugins_folder",
            )
        except Exception as e:
            print(f"{plugin_name} plugin load error: {e}")

    return plugins


load_plugins = get_plugins
