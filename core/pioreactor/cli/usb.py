# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess

import click
from pioreactor.utils import usb as usb_utils


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
            click.echo(f"  source: {update.path}")
    else:
        click.echo("App updates: none")


@usb.command(name="path")
@click.option("--mount", "mountpoint")
def path(mountpoint: str | None) -> None:
    """Print the active Pioreactor-managed USB mount path."""
    try:
        selected_mountpoint = usb_utils.choose_usb_mountpoint(mountpoint)
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(selected_mountpoint)


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
