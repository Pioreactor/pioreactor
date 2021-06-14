# -*- coding: utf-8 -*-
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


def get_plugins():
    """
    This function is really time consuming...
    """
    Plugin = namedtuple("Plugin", ["module", "description", "version", "homepage"])

    eps = entry_points()
    pioreactor_plugins = eps.select(group="pioreactor.plugins")
    plugins = {}
    for plugin in pioreactor_plugins:
        try:
            md = metadata(plugin.name)
            plugins[md["Name"]] = Plugin(
                plugin.load(), md["Summary"], md["Version"], md["Home-page"]
            )
        except Exception as e:
            print(f"{plugin.name} plugin load error: {e}")
    return plugins
