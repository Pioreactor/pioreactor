# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from pioreactor.actions.leader.backup_database import backup_database
from pioreactor.utils import usb as usb_utils
from pioreactor.whoami import get_unit_name


@click.group(short_help="manage USB drives")
def usb() -> None:
    """Manage Pioreactor-controlled USB mounts and USB-backed operations."""


@usb.command(name="list")
@click.option("--json", "json_output", is_flag=True)
def list_usb(json_output: bool) -> None:
    """List removable USB partitions."""
    partitions = usb_utils.discover_usb_partitions()
    if json_output:
        click.echo(json.dumps([partition.as_dict() for partition in partitions]))
        return

    if not partitions:
        click.echo("No removable USB partitions found.")
        return

    click.echo(f"{'Device':16s} {'Name':20s} {'Filesystem':12s} {'Mounted':7s} Mountpoint")
    for partition in partitions:
        mountpoint = partition.mountpoints[0] if partition.mountpoints else ""
        click.echo(
            f"{partition.device:16s} {partition.display_name:20s} "
            f"{(partition.fstype or '-'):12s} {str(partition.is_mounted).lower():7s} {mountpoint}"
        )


@usb.command(name="mount")
@click.option("--device", help="USB partition to mount, for example /dev/sda1")
@click.option("--json", "json_output", is_flag=True)
def mount(device: str | None, json_output: bool) -> None:
    """Mount a removable USB partition under /run/pioreactor/usb."""
    try:
        partition = usb_utils.choose_usb_partition(device)
        mountpoint = usb_utils.mount_usb_partition(partition)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    if json_output:
        payload = partition.as_dict()
        payload["mountpoint"] = str(mountpoint)
        click.echo(json.dumps(payload))
        return

    click.echo(f"Mounted {partition.display_name}.")


@usb.command(name="scan")
@click.option("--mount", "mountpoint")
@click.option("--json", "json_output", is_flag=True)
def scan(mountpoint: str | None, json_output: bool) -> None:
    """Scan a Pioreactor-managed USB mount for known artifacts."""
    try:
        scan_result = usb_utils.scan_usb_mount(usb_utils.choose_usb_mountpoint(mountpoint))
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    if json_output:
        click.echo(json.dumps(scan_result.as_dict()))
        return

    click.echo(f"USB:{scan_result.mountpoint}")
    click.echo(f"Writable: {'yes' if scan_result.writable else 'no'}")
    click.echo(f"Free space: {scan_result.free_bytes / (1024 ** 3):.1f} GB")
    if scan_result.updates:
        click.echo("App updates:")
        for update in scan_result.updates:
            click.echo(f"  {update.path.name} ({update.version})")
    else:
        click.echo("App updates: none")


@usb.command(name="backup-db")
@click.option("--mount", "mountpoint")
@click.option("--force", is_flag=True, help="force backing up even if writes are occurring")
def backup_db(mountpoint: str | None, force: bool) -> None:
    """Back up the local database to USB."""
    try:
        selected_mountpoint = usb_utils.choose_usb_mountpoint(mountpoint)
        destination = usb_utils.build_usb_database_backup_path(
            selected_mountpoint,
            get_unit_name(),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_database(str(destination), force=force, backup_to_workers=0)
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Backed up database to USB:/{destination.relative_to(selected_mountpoint)}.")


@usb.command(name="eject")
@click.option("--device", help="USB partition to eject, for example /dev/sda1")
def eject(device: str | None) -> None:
    """Unmount and eject a Pioreactor-managed USB partition."""
    try:
        partition = usb_utils.choose_usb_partition(device, require_mounted=True)
        usb_utils.eject_usb_partition(partition)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Ejected {partition.display_name}.")


@usb.group(name="update")
def update() -> None:
    """Run updates from USB artifacts."""


@update.command(name="app")
@click.argument("source", required=False)
@click.option("--mount", "mountpoint")
@click.option("--yes", is_flag=True, help="run without confirmation")
def update_app(source: str | None, mountpoint: str | None, yes: bool) -> None:
    """Update the Pioreactor app from a release archive on USB."""
    try:
        update_source = _resolve_update_source(source, mountpoint)
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    if not yes:
        click.confirm(f"Update Pioreactor app from {update_source.name}?", abort=True)

    from pioreactor.cli.pio import update_app as pio_update_app

    callback = pio_update_app.callback
    if callback is None:
        raise click.ClickException("Unable to locate `pio update app` callback.")

    callback(
        branch=None,
        sha=None,
        no_deps=False,
        repo="pioreactor/pioreactor",
        source=str(update_source),
        version=None,
        defer_web_restart=False,
    )
    click.echo(f"Started app update from USB:{update_source.name}.")


def _resolve_update_source(source: str | None, mountpoint: str | None) -> Path:
    if source is not None:
        path = Path(source)
        if not path.is_absolute():
            path = usb_utils.choose_usb_mountpoint(mountpoint) / path
        if not path.is_file():
            raise ValueError(f"{path} does not exist.")
        return path

    scan_result = usb_utils.scan_usb_mount(usb_utils.choose_usb_mountpoint(mountpoint))
    if not scan_result.updates:
        raise ValueError("No release archive found on USB.")
    if len(scan_result.updates) > 1:
        names = ", ".join(update.path.name for update in scan_result.updates)
        raise ValueError(f"Multiple release archives found. Choose one explicitly: {names}")
    return scan_result.updates[0].path
