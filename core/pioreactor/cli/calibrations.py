# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy as copy

import click
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor import structs
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import calibration_protocols
from pioreactor.calibrations import list_devices
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import load_active_calibration
from pioreactor.calibrations import load_calibration
from pioreactor.calibrations.utils import crunch_data_and_confirm_with_user
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import plot_data


def green(string: str) -> str:
    return click.style(string, fg="green")


def bold(string: str) -> str:
    return click.style(string, bold=True)


@click.group(short_help="calibration utils")
def calibration() -> None:
    """
    interface for all calibrations.
    """
    pass


@calibration.command(name="list")
@click.option("--device", required=False)
def list_calibrations(device: str | None) -> None:
    """
    List existing calibrations for the given device if provided, else all.
    """

    header = f"{'Device':<25}{'Name':<50}{'Calibration type':<50}{'Created at':<25}{'Active?':<10}"
    click.echo(header)
    click.echo("-" * len(header))

    if device is None:
        for device in list_devices():
            _display_calibrations_by_device(device)
    else:
        _display_calibrations_by_device(device)


def _display_calibrations_by_device(device: str) -> None:
    calibration_dir = CALIBRATION_PATH / device
    if not calibration_dir.exists():
        click.echo(f"No calibrations found for device '{device}'. Directory does not exist.")
        raise click.Abort()

    calibrations_by_device = list_of_calibrations_by_device(device)

    if len(calibrations_by_device) == 0:
        return

    for name in calibrations_by_device:
        try:
            location = (calibration_dir / name).with_suffix(".yaml")
            data = yaml_decode(location.read_bytes(), type=structs.subclass_union(structs.CalibrationBase))
            row = f"{device:<25}{data.calibration_name:<50}{data.calibration_type:<50}{data.created_at.strftime('%Y-%m-%d %H:%M:%S'):<25}{'✅' if data.is_active(device) else '':<10}"
            click.echo(row)
        except Exception:
            pass
            # error_message = f"Error reading {name}: {e}"
            # click.echo(f"{error_message:<60}")


@calibration.command(name="run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option(
    "--device", "device", required=True, help="Target device of calibration (e.g. od, pump, stirring)."
)
@click.option("--protocol-name", required=False, help="name of protocol, defaults to basic builtin protocol")
@click.option("-y", is_flag=True, help="Skip asking for confirmation for active.")
@click.pass_context
def run_calibration(ctx, device: str, protocol_name: str | None, y: bool) -> None:
    """
    Run an interactive calibration assistant for a specific protocol.
    On completion, stores a YAML file in: /home/pioreactor/.pioreactor/storage/calibrations/<device>/<calibration_name>.yaml
    """

    if "--protocol" in ctx.args:
        raise click.UsageError("Please use --protocol-name instead of --protocol")

    # Dispatch to the assistant function for that device
    if protocol_name is None:
        if len(calibration_protocols.get(device, {}).keys()) == 0:
            click.echo(
                f"No protocols found for device '{device}'. Try `pio calibrations protocols` to see available protocols."
            )
            raise click.Abort()
        if len(calibration_protocols.get(device, {}).keys()) == 1:
            protocol_name = list(calibration_protocols.get(device, {}).keys())[0]
        else:
            # user will choose using click.prompt and click.Choice
            click.clear()
            click.echo()
            click.echo(f"Available protocols for {device}:")
            click.echo()
            for protocol in calibration_protocols.get(device, {}).values():
                click.echo(bold(f"  • {protocol.protocol_name}"))
                click.echo(f"        Description: {protocol.description}")
            click.echo()
            protocol_name = click.prompt(
                green("Choose a protocol"),
                type=click.Choice(list(calibration_protocols.get(device, {}).keys())),
            )

    assistant = calibration_protocols.get(device, {}).get(protocol_name)

    if assistant is None:
        click.echo(
            f"No protocols found for device '{device}'. Available {device} protocols: {list(c[1] for c in calibration_protocols.keys() if c[0] == device)}"
        )
        raise click.Abort()

    calibration_struct = assistant().run(
        target_device=device,
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )

    out_file = calibration_struct.save_to_disk_for_device(device)

    if not y:
        if click.confirm(
            green(f"Do you want to set this calibration as the active calibration for {device}?"),
            default=True,
        ):
            calibration_struct.set_as_active_calibration_for_device(device)
            click.echo(f"Set {calibration_struct.calibration_name} as the active calibration for {device}.")
        else:
            click.echo(
                f"Okay. You can use 'pio calibration set-active --device {device} --name {calibration_struct.calibration_name}' to set this calibration as the active one."
            )
    else:
        calibration_struct.set_as_active_calibration_for_device(device)

    click.echo()
    click.echo(
        f"Calibration '{calibration_struct.calibration_name}' of device '{device}' saved to {out_file} ✅"
    )


@calibration.command(name="protocols")
def list_protocols() -> None:
    """
    List available protocols for device calibrations.
    """
    for device, protocols in calibration_protocols.items():
        click.echo(f"{bold(device)}: {', '.join(protocols.keys())}")


@calibration.command(name="display")
@click.option("--device", required=True, help="Calibration device.")
@click.option("--name", "calibration_name", required=True, help="Name of calibration to display.")
def display_calibration(device: str, calibration_name: str) -> None:
    """
    Display the contents of a calibration YAML file.
    """
    data = load_calibration(device, calibration_name)

    click.echo()
    curve = curve_to_callable(data.curve_type, data.curve_data_)
    plot_data(
        data.recorded_data["x"],
        data.recorded_data["y"],
        calibration_name,
        data.x,
        data.y,
        interpolation_curve=curve,
    )

    click.echo()
    click.echo()
    click.echo("==== YAML output ====")
    click.echo()
    click.echo(yaml_encode(data))


@calibration.command(name="set-active")
@click.option("--device", required=True, help="Which calibration device to set as active.")
@click.option("--name", "calibration_name", required=False, help="Which calibration name to set as active.")
def set_active_calibration(device: str, calibration_name: str | None) -> None:
    """
    Mark a specific calibration as 'active' for that calibration device.
    """

    if calibration_name is None:
        present = load_active_calibration(device)  # type: ignore

        if present is not None:
            click.echo(f"Clearing active calibration for {device}.")
            present.remove_as_active_calibration_for_device(device)
        else:
            click.echo(f"Tried clearing active calibration for {device}, but didn't find one.")

    else:
        data = load_calibration(device, calibration_name)
        data.set_as_active_calibration_for_device(device)


@calibration.command(name="delete")
@click.option("--device", required=True, help="Which calibration device to delete from.")
@click.option("--name", "calibration_name", required=True, help="Which calibration name to delete.")
@click.confirmation_option(prompt=green("Are you sure you want to delete this calibration?"))
def delete_calibration(device: str, calibration_name: str) -> None:
    """
    Delete a calibration file from local storage.

    Example usage:
      calibration delete --device od --name my_od_cal_v1
    """
    target_file = CALIBRATION_PATH / device / f"{calibration_name}.yaml"

    if not target_file.exists():
        click.echo(f"No such calibration file: {target_file}")
        raise click.Abort()

    cal = load_calibration(device, calibration_name)
    cal.remove_as_active_calibration_for_device(device)

    target_file.unlink()

    click.echo(f"Deleted calibration '{calibration_name}' of device '{device}'.")


@calibration.command(name="analyze")
@click.option("--device", required=True, help="Which calibration device to delete from.")
@click.option("--name", "calibration_name", required=True, help="Which calibration name to delete.")
def analyze_calibration(device: str, calibration_name: str) -> None:
    """
    Analyze a calibration file from local storage.
    """
    target_file = CALIBRATION_PATH / device / f"{calibration_name}.yaml"
    if not target_file.exists():
        click.echo(f"No such calibration file: {target_file}")
        raise click.Abort()

    calibration = load_calibration(device, calibration_name)

    if device == "od":
        n = len(calibration.recorded_data["x"])
        weights = [1.0] * n
        weights[0] = n / 2
    else:
        weights = None

    new_calibration = crunch_data_and_confirm_with_user(copy(calibration), initial_degree=3, weights=weights)
    if new_calibration != calibration:
        new_calibration.save_to_disk_for_device(device)
