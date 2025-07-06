# -*- coding: utf-8 -*-
from __future__ import annotations

import glob
import importlib
import importlib.metadata as entry_point
import os
from functools import cache
from typing import Any

import click
from msgspec import Struct

from pioreactor import pubsub
from pioreactor.plugin_management.install_plugin import click_install_plugin
from pioreactor.plugin_management.list_plugins import click_list_plugins
from pioreactor.plugin_management.uninstall_plugin import click_uninstall_plugin
from pioreactor.plugin_management.utils import discover_plugins_in_entry_points
from pioreactor.plugin_management.utils import discover_plugins_in_local_folder
from pioreactor.utils import networking
from pioreactor.whoami import get_unit_name

"""
How do plugins work? There are a few patterns we use to "register" plugins with the core app.

Entry Points

   1. Plugins can use entry_points in the setup, pointing to "pioreactor.plugins"
   2. Automations are defined by a subclassing the respective XXXAutomationContrib. There is a hook in
      this subclass that will add it to an array to be later discovered by `pio run ... `
   3. command-line additions, like background jobs, are found by searching the plugin's namespace for functions
      prepended with `click_`.


Adding to ~/.pioreactor/plugins

   1. Scripts placed in ~/.pioreactor/plugins are automagically loaded in lexicographical order.
     The authors can add metadata to their file with the following variables at the
     highest level in the file:

     __plugin_name__
     __plugin_author__
     __plugin_summary__
     __plugin_version__
     __plugin_homepage__


What's up with the underscore vs dashes discussion in the docs and throughout our software?
https://chat.openai.com/share/fe432411-b1bb-47c3-be0b-8cfcc2588160

"""


class Plugin(Struct):
    module: Any
    description: str
    version: str
    homepage: str
    author: str
    source: str


def get_plugin_api_url(py_file: str) -> str:
    endpoint = f"/unit_api/plugins/installed/{py_file}"
    return pubsub.create_webserver_path(networking.resolve_to_address(get_unit_name()), endpoint)


@cache
def get_plugins() -> dict[str, Plugin]:
    """
    This function is really time consuming...
    """

    plugins: dict[str, Plugin] = {}

    if os.environ.get("SKIP_PLUGINS"):
        # short circuit out
        return plugins

    # get entry point plugins
    # Users can use Python's entry point system to create rich plugins, see
    # example here: https://github.com/Pioreactor/pioreactor-air-bubbler

    for plugin in discover_plugins_in_entry_points():
        try:
            md = entry_point.metadata(plugin.name)
            plugins[md["Name"]] = Plugin(
                plugin.load(),  # plugin loading and execution here.
                md["Summary"],
                md["Version"],
                md["Home-page"],
                md["Author"],
                "entry_points",
            )
        except Exception as e:
            click.secho(f"{plugin.name} plugin load error: {type(e).__name__}: {e}", fg="red")

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

    for py_file in discover_plugins_in_local_folder():
        module_name = py_file.stem
        try:
            module = importlib.import_module(module_name)
            plugin_name = getattr(module, "__plugin_name__", module_name)
            plugins[plugin_name] = Plugin(
                module,
                getattr(module, "__plugin_summary__", BLANK),
                getattr(module, "__plugin_version__", BLANK),
                getattr(module, "__plugin_homepage__", get_plugin_api_url(py_file.name)),
                getattr(module, "__plugin_author__", BLANK),
                f"plugins/{py_file.name}",
            )
        except Exception as e:
            click.secho(f"{py_file} plugin load error: {type(e).__name__}: {e}", fg="red")

    return plugins


load_plugins = get_plugins
