# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor import structs
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import calibration_protocols
from pioreactor.calibrations import list_devices
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import load_calibration
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import plot_data
from pioreactor.utils import local_persistent_storage


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
    if device is None:
        for device in list_devices():
            _display_calibrations_by_device(device)
            click.echo()
            click.echo()
    else:
        _display_calibrations_by_device(device)


def _display_calibrations_by_device(device: str) -> None:
    calibration_dir = CALIBRATION_PATH / device
    if not calibration_dir.exists():
        click.echo(f"No calibrations found for device '{device}'. Directory does not exist.")
        raise click.Abort()

    header = f"{'Device':<25}{'Name':<50}{'Created At':<25}{'Active?':<10}{'Location':<75}"
    click.echo(header)
    click.echo("-" * len(header))

    with local_persistent_storage("active_calibrations") as c:
        for name in list_of_calibrations_by_device(device):
            try:
                location = (calibration_dir / name).with_suffix(".yaml")
                data = yaml_decode(
                    location.read_bytes(), type=structs.subclass_union(structs.CalibrationBase)
                )
                active = c.get(device) == data.calibration_name
                row = f"{device:<25}{data.calibration_name:<50}{data.created_at.strftime('%Y-%m-%d %H:%M:%S'):<25}{'✅' if active else '':<10}{location}"
                click.echo(row)
            except Exception as e:
                error_message = f"Error reading {name}: {e}"
                click.echo(f"{error_message:<60}")


@calibration.command(name="run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option(
    "--device", "device", required=True, help="Target device of calibration (e.g. od, pump, stirring)."
)
@click.option("--protocol-name", required=False, help="name of protocol, defaults to basic builtin protocol")
@click.pass_context
def run_calibration(ctx, device: str, protocol_name: str | None) -> None:
    """
    Run an interactive calibration assistant for a specific protocol.
    On completion, stores a YAML file in: /home/pioreactor/.pioreactor/storage/calibrations/<device>/<calibration_name>.yaml
    """

    if "--protocol" in ctx.args:
        raise click.UsageError("Please use --protocol-name instead of --protocol")

    DEFAULT_PROTOCOLS = {
        "od": "single_vial",
        "media_pump": "duration_based",
        "alt_media_pump": "duration_based",
        "waste_pump": "duration_based",
        "stirring": "dc_based",
    }

    # Dispatch to the assistant function for that device
    if protocol_name is None and device in DEFAULT_PROTOCOLS:
        protocol_name = DEFAULT_PROTOCOLS[device]

    assert protocol_name is not None
    assistant = calibration_protocols.get((device, protocol_name))
    if assistant is None:
        click.echo(
            f"No protocols found for calibration device '{device}'. Available {device} protocols: {list(c[1] for c in calibration_protocols.keys() if c[0] == device)}"
        )
        raise click.Abort()

    # Run the assistant function to get the final calibration data

    calibration_struct = assistant().run(
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )

    out_file = calibration_struct.save_to_disk_for_device(device)

    if click.confirm(
        f"Do you want to set this calibration as the Active Calibration for {device}?", default=True
    ):
        calibration_struct.set_as_active_calibration_for_device(device)

    click.echo(
        f"Calibration '{calibration_struct.calibration_name}' of device '{device}' saved to {out_file} ✅"
    )


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
        click.echo("No calibration name provided. Clearing active calibration.")
        with local_persistent_storage("active_calibrations") as c:
            c.pop(device)

    else:
        data = load_calibration(device, calibration_name)
        data.set_as_active_calibration_for_device(device)


@calibration.command(name="delete")
@click.option("--device", required=True, help="Which calibration device to delete from.")
@click.option("--name", "calibration_name", required=True, help="Which calibration name to delete.")
@click.confirmation_option(prompt="Are you sure you want to delete this calibration?")
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

    target_file.unlink()
    click.echo(f"Deleted calibration '{calibration_name}' of device '{device}'.")

    # TODO: delete from leader and handle updating active?
