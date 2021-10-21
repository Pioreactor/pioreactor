# -*- coding: utf-8 -*-
from json import dumps
import click
import pioreactor


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
                        "version": metadata.version,
                        "description": metadata.description
                        if metadata.description != "UNKNOWN"
                        else None,
                        "homepage": metadata.homepage
                        if metadata.homepage != "UNKNOWN"
                        else None,
                        "source": metadata.source,
                    }
                    for plugin, metadata in pioreactor.plugins.items()
                ]
            )
        )
