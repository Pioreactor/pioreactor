# -*- coding: utf-8 -*-
"""Join or leave a cluster, from the unit itself."""
import subprocess

import click
from pioreactor.exc import UnknownModelAssignedError


@click.group(short_help="join or leave a cluster")
def cluster() -> None:
    pass


@cluster.command(name="join", hidden=True, short_help="point this unit at its new leader")
@click.option("--leader-time", type=int, required=True, help="the leader's clock, in Unix seconds")
@click.option("--model-name", type=str, default=None, help="model name to save")
@click.option("--model-version", type=str, default=None, help="model version to save")
def join(leader_time: int, model_name: str | None, model_version: str | None) -> None:
    """
    Run over SSH by the leader's `pio workers add`, after it copies its shared config.ini here.
    """
    from pioreactor.cluster_membership import join_cluster

    if (model_name is None) != (model_version is None):
        raise click.BadParameter("Provide both --model-name and --model-version.")

    try:
        join_cluster(leader_time, model_name, model_version)
    except (UnknownModelAssignedError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error

    click.echo("Joined the cluster.")


@cluster.command(name="leave", short_help="leave this unit's cluster, then reboot")
@click.option("-y", "--yes", is_flag=True, help="don't ask for confirmation")
def leave(yes: bool) -> None:
    """
    Remove this unit from its leader's inventory, undo `pio cluster join`, and reboot.

    Keeps this unit's model, calibrations, estimators and unit_config.ini. Afterwards the
    unit waits to be added to a cluster again. Stop activities first.
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
        # The leader also asks this unit to leave; leaving twice is harmless.
        delete_from_leader(f"/api/workers/{unit}").raise_for_status()
    except HTTPException as error:
        click.echo(f"Unable to remove {unit} from the leader's inventory ({error}). Leaving anyway.")

    try:
        leave_cluster()
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"{unit} left the cluster. Rebooting.")
    subprocess.run(["sudo", "reboot"])
