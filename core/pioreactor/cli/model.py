# -*- coding: utf-8 -*-
"""Inspect and assign this unit's model without a running web server."""
import json

import click
from pioreactor.exc import UnknownModelAssignedError
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import report_model_to_leader
from pioreactor.unit_model import save_local_model


@click.group(short_help="get or set this unit's model")
def model() -> None:
    pass


@model.command(name="get", short_help="print the local model assignment as JSON")
def get_model() -> None:
    model_name, model_version = get_local_model() or (None, None)
    click.echo(json.dumps({"model_name": model_name, "model_version": model_version}))


@model.command(name="set", short_help="save this unit's model and print it as JSON")
@click.argument("model_name")
@click.argument("model_version")
def set_model(model_name: str, model_version: str) -> None:
    try:
        save_local_model(model_name, model_version)
    except (UnknownModelAssignedError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error

    # Lazy imports keep GET independent of the leader's config and the web/task infrastructure.
    from pioreactor.config import leader_address
    from pioreactor.web.tasks import check_model_hardware

    check_model_hardware(model_name, model_version)
    report_model_to_leader(leader_address, model_name, model_version)
    click.echo(json.dumps({"model_name": model_name, "model_version": model_version}))
