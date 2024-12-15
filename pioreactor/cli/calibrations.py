# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import click
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor.calibrations import calibration_assistants
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import load_calibration
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import plot_data
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import is_testing_env


@click.group(short_help="calibration utils")
def calibration():
    """
    interface for all calibration types.
    """
    pass


@calibration.command(name="list")
@click.option("--type", "cal_type", required=True, help="Filter by calibration type.")
def list_calibrations(cal_type: str):
    """
    List existing calibrations for the given type.
    """
    calibration_dir = CALIBRATION_PATH / cal_type
    if not calibration_dir.exists():
        click.echo(f"No calibrations found for type '{cal_type}'. Directory does not exist.")
        return

    assistant = calibration_assistants.get(cal_type)

    header = f"{'Name':<50}{'Created At':<25}{'Active?':<15}"
    click.echo(header)
    click.echo("-" * len(header))

    with local_persistant_storage("active_calibrations") as c:
        for file in calibration_dir.glob("*.yaml"):
            try:
                data = yaml_decode(file.read_bytes(), type=assistant.calibration_struct)
                active = c.get(cal_type) == data.calibration_name
                row = f"{data.calibration_name:<50}{data.created_at.strftime('%Y-%m-%d %H:%M:%S'):<25}{'✅' if active else '':<15}"
                click.echo(row)
            except Exception as e:
                error_message = f"Error reading {file.stem}: {e}"
                click.echo(f"{error_message:<60}")


@calibration.command(name="run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option("--type", "cal_type", required=True, help="Type of calibration (e.g. od, pump, stirring).")
@click.pass_context
def run_calibration(ctx, cal_type: str):
    """
    Run an interactive calibration assistant for a specific type.
    On completion, stores a YAML file in: /home/pioreactor/.pioreactor/storage/calibrations/<type>/<calibration_name>.yaml
    """

    # Dispatch to the assistant function for that type
    assistant = calibration_assistants.get(cal_type)
    if assistant is None:
        click.echo(
            f"No assistant found for calibration type '{cal_type}'. Available types: {list(calibration_assistants.keys())}"
        )
        raise click.Abort()

    # Run the assistant function to get the final calibration data
    calibration_data = assistant().run(
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )
    calibration_name = calibration_data.calibration_name

    calibration_dir = CALIBRATION_PATH / cal_type
    calibration_dir.mkdir(parents=True, exist_ok=True)
    out_file = calibration_dir / f"{calibration_name}.yaml"

    # Serialize to YAML
    with out_file.open("wb") as f:
        f.write(yaml_encode(calibration_data))

    # TODO: send to leader

    # make active
    with local_persistant_storage("active_calibrations") as c:
        c[cal_type] = calibration_name

    click.echo(f"Calibration '{calibration_name}' of type '{cal_type}' saved to {out_file}")


@calibration.command(name="display")
@click.option("--type", "cal_type", required=True, help="Calibration type.")
@click.option("--name", "calibration_name", required=True, help="Name of calibration to display.")
def display_calibration(cal_type: str, calibration_name: str):
    """
    Display the contents of a calibration YAML file.
    """
    data = load_calibration(cal_type, calibration_name)

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
@click.option("--type", "cal_type", required=True, help="Which calibration type to set as active.")
@click.option("--name", "calibration_name", required=False, help="Which calibration name to set as active.")
def set_active_calibration(cal_type: str, calibration_name: str | None):
    """
    Mark a specific calibration as 'active' for that calibration type.
    """

    if calibration_name is None:
        click.echo("No calibration name provided. Clearing active calibration.")
        with local_persistant_storage("active_calibrations") as c:
            c.pop((cal_type, None))

    else:
        data = load_calibration(cal_type, calibration_name)

        with local_persistant_storage("active_calibrations") as c:
            c[data.calibration_type] = data.calibration_name


@calibration.command(name="delete")
@click.option("--type", "cal_type", required=True, help="Which calibration type to delete from.")
@click.option("--name", "calibration_name", required=True, help="Which calibration name to delete.")
@click.confirmation_option(prompt="Are you sure you want to delete this calibration?")
def delete_calibration(cal_type: str, calibration_name: str):
    """
    Delete a calibration file from local storage.

    Example usage:
      calibration delete --type od --name my_od_cal_v1
    """
    target_file = CALIBRATION_PATH / cal_type / f"{calibration_name}.yaml"
    if not target_file.exists():
        click.echo(f"No such calibration file: {target_file}")
        raise click.Abort()

    target_file.unlink()
    click.echo(f"Deleted calibration '{calibration_name}' of type '{cal_type}'.")

    # TODO: delete from leader and handle updating active?
