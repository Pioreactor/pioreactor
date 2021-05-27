# -*- coding: utf-8 -*-
from json import dumps
import click
import pioreactor
from .install_plugin import click_install_plugin
from .uninstall_plugin import click_uninstall_plugin

__all__ = ("click_uninstall_plugin", "click_install_plugin")


@click.command(name="list-plugins", short_help="list the installed plugins")
@click.option("--json", is_flag=True, help="output as json")
def click_list_plugins(json):

    if not json:
        for plugin in pioreactor.plugins.keys():
            click.echo(plugin)

    else:
        click.echo(
            dumps(
                [
                    {
                        "name": plugin,
                        "description": metadata.description
                        if metadata.description != "UNKNOWN"
                        else None,
                        "version": metadata.version,
                        "homepage": metadata.homepage
                        if metadata.homepage != "UNKNOWN"
                        else None,
                    }
                    for plugin, metadata in pioreactor.plugins.items()
                ]
            )
        )
