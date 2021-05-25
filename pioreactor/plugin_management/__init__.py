# -*- coding: utf-8 -*-
import click
import pioreactor
from .install_plugin import click_install_plugin
from .uninstall_plugin import click_uninstall_plugin

__all__ = ("click_uninstall_plugin", "click_install_plugin")


@click.command(name="list-plugins", short_help="list the installed plugins")
def click_list_plugins():

    for plugin in pioreactor.plugins.keys():
        click.echo(plugin)
