# -*- coding: utf-8 -*-
from __future__ import annotations

from json import dumps

import click


def list_plugins_as_json() -> str:
    # this is to initialize all the modules, to plugins don't fail when being loaded.
    from pioreactor.cli import run  # noqa: F403, F401
    from pioreactor.plugin_management import get_plugins

    return dumps(
        [
            {
                "name": plugin,
                "version": metadata.version,
                "description": metadata.description if metadata.description != "UNKNOWN" else None,
                "homepage": metadata.homepage if metadata.homepage != "UNKNOWN" else None,
                "source": metadata.source,
                "author": metadata.author if metadata.author != "UNKNOWN" else None,
            }
            for plugin, metadata in get_plugins().items()
        ]
    )


@click.command(name="list", short_help="list the installed plugins")
@click.option("--json", is_flag=True, help="output as json")
def click_list_plugins(json: bool) -> None:
    # this is to initialize all the modules, to plugins don't fail when being loaded.
    from pioreactor.cli import run  # noqa: F403, F401
    from pioreactor.plugin_management import get_plugins

    if not json:
        for plugin, metadata in get_plugins().items():
            click.echo(f"{plugin}=={metadata.version}")

    else:
        click.echo(list_plugins_as_json())
