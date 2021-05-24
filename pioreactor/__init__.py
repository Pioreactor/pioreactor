# -*- coding: utf-8 -*-
try:
    from importlib.metadata import entry_points
except ImportError:  # TODO: this is available in 3.8+
    from importlib_metadata import entry_points

from pioreactor.version import __version__  # noqa: F401
from pioreactor.background_jobs import *  # noqa: F401,F403
from pioreactor.actions import *  # noqa: F401,F403

# needed to import to "load" the automation subclasses,
# and hence the *-controller will register them.
from pioreactor.automations import *  # noqa: F401,F403


def get_plugins():
    pioreactor_plugins = entry_points().get("pioreactor.plugins", [])
    plugins = {}
    for plugin in pioreactor_plugins:
        plugins[plugin.name] = plugin.load()
    return plugins


plugins = get_plugins()
