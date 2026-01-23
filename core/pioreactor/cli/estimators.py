# -*- coding: utf-8 -*-
import click
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations import get_calibration_protocols
from pioreactor.estimators import ESTIMATOR_PATH
from pioreactor.estimators import list_estimator_devices
from pioreactor.estimators import list_of_estimators_by_device
from pioreactor.estimators import load_active_estimator
from pioreactor.estimators import load_estimator


def green(string: str) -> str:
    return click.style(string, fg="green")


def bold(string: str) -> str:
    return click.style(string, bold=True)


@click.group(short_help="estimator utils")
def estimators() -> None:
    """
    interface for all estimators.
    """
    pass


@estimators.command(name="list")
@click.option("--device", required=False)
def list_estimators(device: str | None) -> None:
    """
    List existing estimators for the given device if provided, else all.
    """

    header = f"{'Device':<25}{'Name':<50}{'Estimator type':<50}{'Created at':<25}{'Active?':<10}"
    click.echo(header)
    click.echo("-" * len(header))

    if device is None:
        for device in list_estimator_devices():
            _display_estimators_by_device(device)
    else:
        _display_estimators_by_device(device)


def _display_estimators_by_device(device: str) -> None:
    estimator_dir = ESTIMATOR_PATH / device
    if not estimator_dir.exists():
        click.echo(
            f"No estimators found for device '{device}'. Directory does not exist.",
            err=True,
        )
        return

    estimators_by_device = list_of_estimators_by_device(device)

    if len(estimators_by_device) == 0:
        return

    for name in estimators_by_device:
        try:
            location = (estimator_dir / name).with_suffix(".yaml")
            data = yaml_decode(location.read_bytes(), type=structs.subclass_union(structs.EstimatorBase))
            row = (
                f"{device:<25}{data.estimator_name:<50}{data.estimator_type:<50}"
                f"{data.created_at.strftime('%Y-%m-%d %H:%M:%S'):<25}{'✅' if data.is_active(device) else '':<10}"
            )
            click.echo(row)
        except Exception:
            pass
            # error_message = f"Error reading {name}: {e}"
            # click.echo(f"{error_message:<60}")


@estimators.command(name="protocols")
def list_protocols() -> None:
    """
    List available protocols for estimator workflows.
    """
    estimator_devices = [pt.OD_FUSED_DEVICE]
    shown = False
    for device in estimator_devices:
        protocols = get_calibration_protocols().get(device, {})
        if not protocols:
            continue
        click.echo(f"{bold(device)}: {', '.join(protocols.keys())}")
        shown = True

    if not shown:
        click.echo("No estimator protocols found.")


@estimators.command(name="set-active")
@click.option("--device", required=True, help="Which estimator device to set as active.")
@click.option("--name", "estimator_name", required=False, help="Which estimator name to set as active.")
def set_active_estimator(device: str, estimator_name: str | None) -> None:
    """
    Mark a specific estimator as 'active' for that estimator device.
    """

    if estimator_name is None:
        present = load_active_estimator(device)  # type: ignore

        if present is not None:
            click.echo(f"Clearing active estimator for {device}.")
            present.remove_as_active_calibration_for_device(device)
        else:
            click.echo(f"Tried clearing active estimator for {device}, but didn't find one.")

    else:
        data = load_estimator(device, estimator_name)
        data.set_as_active_calibration_for_device(device)


@estimators.command(name="delete")
@click.option("--device", required=True, help="Which estimator device to delete from.")
@click.option("--name", "estimator_name", required=True, help="Which estimator name to delete.")
@click.confirmation_option(prompt=green("Are you sure you want to delete this estimator?"))
def delete_estimator(device: str, estimator_name: str) -> None:
    """
    Delete an estimator file from local storage.

    Example usage:
      estimators delete --device od_fused --name my_estimator_v1
    """
    target_file = ESTIMATOR_PATH / device / f"{estimator_name}.yaml"

    if not target_file.exists():
        click.echo(f"No such estimator file: {target_file}")
        raise click.Abort()

    estimator = load_estimator(device, estimator_name)
    estimator.remove_as_active_calibration_for_device(device)

    target_file.unlink()

    click.echo(f"Deleted estimator '{estimator_name}' of device '{device}'.")
