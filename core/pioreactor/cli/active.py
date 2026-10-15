# -*- coding: utf-8 -*-
"""Inspect and change whether this unit is in service, without a running web server."""
import json

import click
from pioreactor.unit_active import adopt_leader_active
from pioreactor.unit_active import is_locally_active
from pioreactor.unit_active import report_active_to_leader
from pioreactor.unit_active import save_local_active


@click.group(short_help="get or set whether this unit is active")
def active() -> None:
    pass


@active.command(name="get", short_help="print whether this unit is active as JSON")
def get_active() -> None:
    click.echo(json.dumps({"is_active": int(is_locally_active())}))


@active.command(name="set", short_help="set whether this unit is active; 0 stops its activities")
@click.argument("is_active", type=click.IntRange(0, 1))
def set_active(is_active: int) -> None:
    save_local_active(bool(is_active))

    # Lazy import keeps GET independent of the leader's config.
    from pioreactor.config import leader_address

    if not report_active_to_leader(leader_address, bool(is_active)):
        click.echo("Unable to tell the leader. Run this again once the leader is reachable.", err=True)
    click.echo(json.dumps({"is_active": is_active}))


@active.command(name="adopt", hidden=True, short_help="save the leader's record of this")
def adopt_active() -> None:
    """
    Save the leader's record of whether this unit is active. Run by the update that moved ownership
    of `is_active` from the leader to each unit.
    """
    from pioreactor.mureq import HTTPException

    try:
        is_active = adopt_leader_active()
    except HTTPException as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps({"is_active": int(is_active)}))
