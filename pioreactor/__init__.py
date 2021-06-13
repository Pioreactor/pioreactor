# -*- coding: utf-8 -*-
try:
    from importlib.metadata import entry_points, metadata
except ImportError:  # TODO: this is available in 3.8+
    from importlib_metadata import entry_points, metadata

from collections import namedtuple

from pioreactor.version import __version__  # noqa: F401
from pioreactor.background_jobs import (  # noqa: F401,F403
    growth_rate_calculating,  # noqa: F401,F403
    dosing_control,  # noqa: F401,F403
    led_control,  # noqa: F401,F403
    temperature_control,  # noqa: F401,F403
    od_reading,  # noqa: F401,F403
    stirring,  # noqa: F401,F403
    monitor,  # noqa: F401,F403
    mqtt_to_db_streaming,  # noqa: F401,F403
    watchdog,  # noqa: F401,F403
)  # noqa: F401,F403

# from pioreactor.actions import *  # noqa: F401,F403

# needed to import to "load" the automation subclasses,
# and hence the *-controller will register them.
from pioreactor.automations import dosing, led, temperature, events  # noqa: F401,F403


def get_plugins():

    Plugin = namedtuple("Plugin", ["module", "description", "version", "homepage"])

    pioreactor_plugins = entry_points().get("pioreactor.plugins", [])
    plugins = {}
    for plugin in pioreactor_plugins:
        try:
            md = metadata(plugin.name)
            plugins[md["Name"]] = Plugin(
                plugin.load(), md["Summary"], md["Version"], md["Home-page"]
            )
        except Exception as e:
            print(e)
    return plugins


plugins = get_plugins()
