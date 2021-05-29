# -*- coding: utf-8 -*-
"""
How do plugins work? There are a few patterns we use to "register" plugins with the core app.


1. All plugins should use entry_points in the setup, pointing to "pioreactor.plugins"
2. Automations are defined by a subclassing the respective XXXAutomationContrib. There is a hook in
   this parent class that will add the subclass to XXXController, hence the Controller will know about
   it and be able to run it (as the module is loaded in pioreactor.__init__.py)
3. command-line additions, like background jobs, are found by searching the plugin's namespace for functions
   prepended with `click_`.



"""

from .install_plugin import click_install_plugin
from .uninstall_plugin import click_uninstall_plugin
from .list_plugins import click_list_plugins

__all__ = ("click_uninstall_plugin", "click_install_plugin", "click_list_plugins")
