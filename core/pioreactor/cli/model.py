# -*- coding: utf-8 -*-
"""Inspect and assign this unit's model without a running web server."""
import json

import click
from pioreactor.exc import UnknownModelAssignedError
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import save_local_model


@click.group(short_help="get or set this unit's model")
def model() -> None:
    pass


@model.command(name="get", short_help="print the local model assignment as JSON")
def get_model() -> None:
    name, version = get_local_model() or (None, None)
    click.echo(json.dumps({"model_name": name, "model_version": version}))


@model.command(name="set", short_help="save this unit's model and print it as JSON")
@click.argument("name")
@click.argument("version")
def set_model(name: str, version: str) -> None:
    try:
        save_local_model(name, version)
    except (UnknownModelAssignedError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error

    # Lazy import keeps GET independent of the web/task infrastructure.
    from pioreactor.web.tasks import check_model_hardware

    check_model_hardware(name, version)
    click.echo(json.dumps({"model_name": name, "model_version": version}))
