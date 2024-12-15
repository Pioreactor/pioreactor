# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import click
from msgspec.yaml import decode as yaml_decode
from msgspec.yaml import encode as yaml_encode

from pioreactor import structs
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import plot_data
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import is_testing_env

if not is_testing_env():
    CALIBRATION_PATH = Path("/home/pioreactor/.pioreactor/storage/calibrations/")
else:
    CALIBRATION_PATH = Path(".pioreactor/storage/calibrations/")

# Lookup table for different calibration assistants
CALIBRATION_ASSISTANTS = {}


class CalibrationAssistant:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        CALIBRATION_ASSISTANTS[cls.target_calibration_type] = cls

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method.")


class ODAssistant(CalibrationAssistant):
    target_calibration_type = "od"
    calibration_struct = structs.ODCalibration

    def __init__(self):
        pass


class PumpAssistant(CalibrationAssistant):
    target_calibration_type = "pump"
    calibration_struct = structs.PumpCalibration

    def __init__(self):
        pass


class StirringAssistant(CalibrationAssistant):
    target_calibration_type = "stirring"
    calibration_struct = structs.StirringCalibration

    def __init__(self):
        pass

    def run(self, min_dc: str | None = None, max_dc: str | None = None) -> structs.StirringCalibration:
        from pioreactor.calibrations.stirring_calibration import run_stirring_calibration

        return run_stirring_calibration(
            min_dc=float(min_dc) if min_dc is not None else None, max_dc=float(max_dc) if max_dc else None
        )


@click.group(short_help="calibration utils")
def calibration():
    """
    Calibration CLI - A unified interface for all calibration types.
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

    assistant = CALIBRATION_ASSISTANTS.get(cal_type)

    header = f"{'Name':<50}{'Created At':<25}{'Subtype':<15}{'Current?':<15}"
    click.echo(header)
    click.echo("-" * len(header))

    with local_persistant_storage("current_calibrations") as c:
        for file in calibration_dir.glob("*.yaml"):
            try:
                data = yaml_decode(file.read_bytes(), type=assistant.calibration_struct)
                current = c.get((cal_type, data.calibration_subtype)) == data.calibration_name
                row = f"{data.calibration_name:<50}{data.created_at.strftime('%Y-%m-%d %H:%M:%S'):<25}{data.calibration_subtype or '':<15}{'✅' if current else '':<15}"
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
    assistant = CALIBRATION_ASSISTANTS.get(cal_type)
    if assistant is None:
        click.echo(f"No assistant found for calibration type '{cal_type}'.")
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

    click.echo(f"Calibration '{calibration_name}' of type '{cal_type}' saved to {out_file}")


@calibration.command(name="display")
@click.option("--type", "cal_type", required=True, help="Calibration type.")
@click.option("--name", "calibration_name", required=True, help="Name of calibration to display.")
def display_calibration(cal_type: str, calibration_name: str):
    """
    Display the contents of a calibration YAML file.
    """
    file = CALIBRATION_PATH / cal_type / f"{calibration_name}.yaml"
    if not file.exists():
        click.echo(f"No such calibration file: {file}")
        raise click.Abort()

    assistant = CALIBRATION_ASSISTANTS.get(cal_type)

    try:
        data = yaml_decode(file.read_bytes(), type=assistant.calibration_struct)
    except Exception as e:
        click.echo(f"Error reading {file.stem()}: {e}")

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
    click.echo(file.read_text())


@calibration.command(name="set-current")
@click.option("--type", "cal_type", required=True, help="Which calibration type to set as current.")
@click.option("--name", "calibration_name", required=True, help="Which calibration name to set as current.")
def set_current_calibration(cal_type: str, calibration_name: str):
    """
    Mark a specific calibration as 'current' for that calibration type.
    """

    file = CALIBRATION_PATH / cal_type / f"{calibration_name}.yaml"

    # Dispatch to the assistant function for that type
    assistant = CALIBRATION_ASSISTANTS.get(cal_type)
    if assistant is None:
        click.echo(f"No assistant found for calibration type '{cal_type}'.")
        raise click.Abort()

    try:
        data = yaml_decode(file.read_bytes(), type=assistant.calibration_struct)
    except Exception as e:
        click.echo(f"Error reading {file.stem()}: {e}")

    with local_persistant_storage("current_calibrations") as c:
        c[(cal_type, data.calibration_subtype)] = calibration_name


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
