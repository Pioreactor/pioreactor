# -*- coding: utf-8 -*-
from json import dumps
import click


@click.command(name="list-plugins", short_help="list the installed plugins")
@click.option("--json", is_flag=True, help="output as json")
def click_list_plugins(json) -> None:
    from pioreactor.plugin_management import get_plugins

    if not json:
        for plugin in get_plugins().keys():
            click.echo(plugin)

    else:
        click.echo(
            dumps(
                [
                    {
                        "name": plugin,
                        "version": metadata.version,
                        "description": metadata.description
                        if metadata.description != "UNKNOWN"
                        else None,
                        "homepage": metadata.homepage
                        if metadata.homepage != "UNKNOWN"
                        else None,
                        "source": metadata.source,
                    }
                    for plugin, metadata in get_plugins().items()
                ]
            )
        )
