# -*- coding: utf-8 -*-
import click
from pioreactor import plugin_management


@click.group(short_help="manage plugins")
def plugins():
    pass


plugins.add_command(plugin_management.click_install_plugin)
plugins.add_command(plugin_management.click_uninstall_plugin)
plugins.add_command(plugin_management.click_list_plugins)
