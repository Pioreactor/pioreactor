# -*- coding: utf-8 -*-
import click
from pioreactor.plugin_management.install_plugin import click_install_plugin
from pioreactor.plugin_management.list_plugins import click_list_plugins
from pioreactor.plugin_management.uninstall_plugin import click_uninstall_plugin


@click.group(short_help="manage plugins")
def plugins() -> None:
    pass


plugins.add_command(click_install_plugin)
plugins.add_command(click_uninstall_plugin)
plugins.add_command(click_list_plugins)
