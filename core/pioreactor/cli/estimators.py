# -*- coding: utf-8 -*-
from copy import copy
from math import sqrt

import click
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations import get_calibration_protocols
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import curve_to_functional_form
from pioreactor.estimators import ESTIMATOR_PATH
from pioreactor.estimators import list_estimator_devices
from pioreactor.estimators import list_of_estimators_by_device
from pioreactor.estimators import load_active_estimator
from pioreactor.estimators import load_estimator
from pioreactor.utils.akimas import akima_eval
from pioreactor.utils.akimas import akima_fit


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
        sorted_protocols = sorted(
            protocols.values(),
            key=lambda protocol: (getattr(protocol, "priority", 99), protocol.protocol_name),
        )
        protocol_names = [protocol.protocol_name for protocol in sorted_protocols]
        click.echo(f"{bold(device)}: {', '.join(protocol_names)}")
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


def _extract_fusion_by_angle_records(
    estimator: structs.ODFusionEstimator,
) -> dict[pt.PdAngle, dict[str, list[float]]]:
    recorded_data = estimator.recorded_data
    if isinstance(recorded_data, dict) and "by_angle" in recorded_data:
        by_angle = recorded_data.get("by_angle")
        if isinstance(by_angle, dict):
            return {angle: value for angle, value in by_angle.items() if isinstance(value, dict)}

    if isinstance(recorded_data, dict) and "base_recorded_data" in recorded_data:
        base_recorded_data = recorded_data.get("base_recorded_data")
        if isinstance(base_recorded_data, dict) and "by_angle" in base_recorded_data:
            by_angle = base_recorded_data.get("by_angle")
            if isinstance(by_angle, dict):
                return {angle: value for angle, value in by_angle.items() if isinstance(value, dict)}

    return {}


def _fit_curve_data_from_points(
    *,
    fit: str,
    x: list[float],
    y: list[float],
) -> structs.AkimaFitData:
    if len(x) < 2 or len(y) < 2:
        raise ValueError("Need at least two points to fit a curve.")

    if fit == "akima":
        return akima_fit(x, y)
    raise ValueError(f"Unsupported fit type: {fit}")


def _rmse_for_fit(curve_data: structs.CalibrationCurveData, x: list[float], y: list[float]) -> float:
    curve_callable = curve_to_callable(curve_data)
    residuals = [(curve_callable(x_val) - y_val) ** 2 for x_val, y_val in zip(x, y)]
    if not residuals:
        return 0.0
    return sqrt(sum(residuals) / len(residuals))


@estimators.command(name="analyze")
@click.option("--device", required=True, help="Which estimator device to analyze.")
@click.option("--name", "estimator_name", required=True, help="Which estimator name to analyze.")
@click.option(
    "--fit",
    "fit",
    default="akima",
    type=click.Choice(["poly", "spline", "akima"]),
    show_default=True,
    help="Curve fit type to use when analyzing.",
)
def analyze_estimator(device: str, estimator_name: str, fit: str) -> None:
    """
    Analyze an estimator file from local storage.
    """
    target_file = ESTIMATOR_PATH / device / f"{estimator_name}.yaml"
    if not target_file.exists():
        click.echo(f"No such estimator file: {target_file}", err=True)
        raise SystemExit(1)

    try:
        estimator = load_estimator(device, estimator_name)
    except Exception as exc:
        click.echo(f"Unable to load estimator: {exc}", err=True)
        raise SystemExit(1) from exc

    if not isinstance(estimator, structs.ODFusionEstimator):
        click.echo("Only od_fused estimators are supported for analyze.", err=True)
        raise SystemExit(1)

    if fit != "akima":
        click.echo("Only akima fits are supported for od_fused estimators.", err=True)
        raise SystemExit(1)

    by_angle = _extract_fusion_by_angle_records(estimator)
    if not by_angle:
        click.echo("No recorded fusion data available to analyze.", err=True)
        raise SystemExit(1)

    click.echo(f"Estimator: {estimator.estimator_name}")
    click.echo(f"Device: {device}")
    click.echo(f"Fit: {fit}")
    click.echo("")

    new_estimator = copy(estimator)
    mu_splines: dict[pt.PdAngle, structs.AkimaFitData] = {}
    sigma_splines_log: dict[pt.PdAngle, structs.AkimaFitData] = {}

    for angle in estimator.angles:
        points = by_angle.get(angle)
        if not points:
            click.echo(f"{angle}°: no recorded data found.", err=True)
            continue

        x_vals = points.get("x")
        y_vals = points.get("y")
        if not isinstance(x_vals, list) or not isinstance(y_vals, list):
            click.echo(f"{angle}°: recorded data malformed.", err=True)
            continue

        try:
            mu_curve = _fit_curve_data_from_points(fit=fit, x=x_vals, y=y_vals)
            mu_rmse = _rmse_for_fit(mu_curve, x_vals, y_vals)
        except Exception as exc:
            click.echo(f"{angle}°: unable to fit mu curve: {exc}", err=True)
            raise SystemExit(1) from exc

        sigma_reference = [akima_eval(estimator.sigma_splines_log[angle], float(x_val)) for x_val in x_vals]
        try:
            sigma_curve = _fit_curve_data_from_points(fit=fit, x=x_vals, y=sigma_reference)
            sigma_rmse = _rmse_for_fit(sigma_curve, x_vals, sigma_reference)
        except Exception as exc:
            click.echo(f"{angle}°: unable to fit sigma curve: {exc}", err=True)
            raise SystemExit(1) from exc

        click.echo(f"{angle}° mu: {curve_to_functional_form(mu_curve)}")
        click.echo(f"{angle}° mu rmse: {mu_rmse:0.4f}")
        click.echo(f"{angle}° sigma(log): {curve_to_functional_form(sigma_curve)}")
        click.echo(f"{angle}° sigma(log) rmse: {sigma_rmse:0.4f}")
        click.echo("")

        mu_splines[angle] = mu_curve
        sigma_splines_log[angle] = sigma_curve

    confirm = click.confirm(green("Save updated estimator fit?"), default=False)
    if not confirm:
        raise SystemExit(0)

    new_estimator.mu_splines = mu_splines
    new_estimator.sigma_splines_log = sigma_splines_log
    new_estimator.save_to_disk_for_device(device)
