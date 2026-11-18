# -*- coding: utf-8 -*-
"""Join or leave a cluster, from the unit itself."""
import sqlite3
import subprocess
from configparser import Error
from pathlib import Path

import click
from pioreactor.exc import UnknownModelAssignedError


@click.group(short_help="join or leave a cluster")
def cluster() -> None:
    pass


@cluster.command(name="join", hidden=True, short_help="point this unit at its new leader")
@click.option("--leader-time", type=int, required=True, help="the leader's clock, in Unix seconds")
@click.option("--model-name", type=str, default=None, help="model name to save")
@click.option("--model-version", type=str, default=None, help="model version to save")
@click.option("--staged-config", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
def join(
    leader_time: int,
    model_name: str | None,
    model_version: str | None,
    staged_config: Path,
) -> None:
    """
    Read the staged shared config. Run over SSH by the leader's `pio workers add`.
    """
    from pioreactor.cluster_membership import join_cluster

    if (model_name is None) != (model_version is None):
        raise click.BadParameter("Provide both --model-name and --model-version.")

    try:
        join_cluster(
            staged_config.read_text(encoding="utf-8"),
            leader_time,
            model_name,
            model_version,
        )
    except (UnknownModelAssignedError, RuntimeError, Error, OSError, sqlite3.Error, UnicodeError) as error:
        raise click.ClickException(str(error)) from error

    click.echo("Joined the cluster.")


@cluster.command(name="leave", short_help="leave this unit's cluster, then reboot")
@click.option("-y", "--yes", is_flag=True, help="don't ask for confirmation")
def leave(yes: bool) -> None:
    """
    Remove this unit from its leader's inventory, undo `pio cluster join`, and reboot.

    Keeps this unit's model, calibrations, estimators and unit settings. Leader-capable
    units restore their standalone config. Stop activities first.
    """
    from pioreactor.cluster_membership import check_can_leave
    from pioreactor.cluster_membership import leave_cluster
    from pioreactor.mureq import HTTPException
    from pioreactor.pubsub import delete_from_leader
    from pioreactor.whoami import get_unit_name

    unit = get_unit_name()
    try:
        # Before telling the leader, which would remove this unit from its inventory.
        check_can_leave()
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    if not yes:
        click.confirm(f"Remove {unit} from its cluster and reboot it?", abort=True)

    try:
        delete_from_leader(f"/api/workers/{unit}").raise_for_status()
    except HTTPException as error:
        click.echo(f"Unable to remove {unit} from the leader's inventory ({error}). Leaving anyway.")

    try:
        changed = leave_cluster()
    except (RuntimeError, Error, OSError) as error:
        raise click.ClickException(str(error)) from error

    if not changed:
        click.echo(f"{unit} already left its cluster.")
        return
    click.echo(f"{unit} left the cluster. Rebooting.")
    subprocess.run(["sudo", "reboot"])
