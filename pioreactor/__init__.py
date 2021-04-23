# -*- coding: utf-8 -*-
from importlib.metadata import entry_points
from pioreactor.version import __version__  # noqa: F401


def get_plugins():
    pioreactor_plugins = entry_points()["pioreactor.plugins"]
    plugins = {}
    for plugin in pioreactor_plugins:
        plugins[plugin.name] = plugin.load()
    return plugins


plugins = get_plugins()
