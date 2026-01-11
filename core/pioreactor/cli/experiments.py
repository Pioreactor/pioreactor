# -*- coding: utf-8 -*-
import click
from pioreactor.pubsub import delete_from_leader
from pioreactor.pubsub import get_from_leader
from pioreactor.pubsub import post_into_leader
from pioreactor.whoami import am_I_leader


@click.group(short_help="manage experiments")
def experiments() -> None:
    """Experiment operations (leader only)."""
    if not am_I_leader():
        raise click.UsageError("This command is only available on the leader.")


@experiments.command(name="create", short_help="create a new experiment")
@click.argument("name", nargs=1, required=True)
def create_experiment(name: str) -> None:
    """Create a new experiment with the given NAME (leader only)."""
    if not am_I_leader():
        raise click.UsageError("This command is only available on the leader.")

    try:
        resp = post_into_leader("/api/experiments", json={"experiment": name})
    except Exception as e:
        raise click.ClickException(str(e))

    if resp.status_code in (200, 201):
        click.echo(f"Created experiment: {name}")
    elif resp.status_code == 409:
        raise click.ClickException(f"Experiment '{name}' already exists (409)")
    elif resp.status_code == 400:
        # try to show server error message if available
        msg = resp.json().get("error")
        raise click.ClickException(f"Invalid experiment name. {msg}")
    else:
        raise click.ClickException(f"Failed to create experiment '{name}' (HTTP {resp.status_code})")


@experiments.command(name="list", short_help="list experiments")
@click.option("--verbose", "-v", is_flag=True, help="show creation time and description")
def list_experiments(verbose: bool) -> None:
    """List experiments on the leader."""
    if not am_I_leader():
        raise click.UsageError("This command is only available on the leader.")

    try:
        resp = get_from_leader("/api/experiments")
    except Exception as e:
        raise click.ClickException(str(e))

    if not resp.ok:
        raise click.ClickException(f"Failed to list experiments (HTTP {resp.status_code})")

    try:
        experiments = resp.json()
    except Exception:
        experiments = []

    if not experiments:
        click.echo("No experiments found")
        return

    for row in experiments:
        name = row.get("experiment")
        if verbose:
            created = row.get("created_at", "")
            desc = row.get("description", "") or ""
            click.echo(f"{name}\t{created}\t{desc}")
        else:
            click.echo(name)


@experiments.command(name="delete", short_help="delete an experiment")
@click.argument("name", nargs=1, required=True)
@click.option("--yes", "-y", is_flag=True, help="do not prompt for confirmation")
def delete_experiment(name: str, yes: bool) -> None:
    """Delete an experiment by NAME (leader only)."""
    if not am_I_leader():
        raise click.UsageError("This command is only available on the leader.")

    if not yes:
        if not click.confirm(
            f"Delete experiment '{name}'? This will stop jobs in that experiment.", default=False
        ):
            raise click.Abort()

    try:
        resp = delete_from_leader(f"/api/experiments/{name}")
    except Exception as e:
        raise click.ClickException(str(e))

    if resp.status_code == 200:
        click.echo(f"Deleted experiment: {name}")
    elif resp.status_code == 404:
        raise click.ClickException(f"Experiment '{name}' not found (404)")
    else:
        raise click.ClickException(f"Failed to delete experiment '{name}' (HTTP {resp.status_code})")
