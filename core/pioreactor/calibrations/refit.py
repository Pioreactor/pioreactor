# -*- coding: utf-8 -*-
"""Refit using only the measurements and fit parameters persisted in the calibration YAML.

The artifact must contain everything needed to recreate its curve: complete recorded
measurements, their inclusion mask, and the curve family and parameters. No implicit
blank anchors or external weights are applied.
"""
from math import isfinite
from typing import Literal
from warnings import catch_warnings
from warnings import simplefilter

from msgspec.structs import replace
from pioreactor import structs
from pioreactor.utils.akimas import akima_fit
from pioreactor.utils.polys import poly_fit
from pioreactor.utils.splines import _build_spline_design_matrix
from pioreactor.utils.splines import spline_fit


def refit_calibration(
    calibration: structs.CalibrationBase,
    included: list[bool],
    y_values: list[float] | None = None,
    x_values: list[float] | None = None,
) -> structs.CalibrationBase:
    candidate = replace(calibration, included=included)
    candidate.__post_init__()
    candidate.recorded_data = dict(calibration.recorded_data)
    updates: dict[Literal["x", "y"], list[float] | None] = {"x": x_values, "y": y_values}
    for axis, values in updates.items():
        if values is not None:
            if len(values) != len(calibration.recorded_data[axis]):
                raise ValueError(f"Provide one {axis} value per recorded measurement.")
            if not all(isfinite(value) for value in values):
                raise ValueError(f"Recorded {axis} values must be finite numbers.")
            candidate.recorded_data[axis] = list(values)
    data = candidate.included_recorded_data()
    x, y = data["x"], data["y"]
    if not all(isfinite(value) for value in x + y):
        raise ValueError("Included measurements must be finite numbers.")

    curve = calibration.curve_data_
    # Fitters need NumPy only while recalculating, never when reading artifacts.
    import numpy as np

    with catch_warnings():
        simplefilter("error", np.exceptions.RankWarning)
        if isinstance(curve, structs.PolyFitCoefficients):
            degree = len(curve.coefficients) - 1
            if degree < 0:
                raise ValueError("The saved polynomial has no coefficients.")
            if len(set(x)) < degree + 1:
                raise ValueError(f"Include at least {degree + 1} distinct x values for this polynomial.")
            candidate.curve_data_ = poly_fit(x, y, degree=degree)
        elif isinstance(curve, structs.SplineFitData):
            if len(set(x)) < len(curve.knots):
                raise ValueError(f"Include at least {len(curve.knots)} distinct x values for this spline.")
            # If included x coordinates change, relocate knots using the same knot count.
            # Persist the resulting positions so the curve remains reproducible.
            x_changed = any(
                keep and before != after
                for keep, before, after in zip(
                    included, calibration.recorded_data["x"], candidate.recorded_data["x"]
                )
            )
            fitted_spline = spline_fit(x, y, knots=len(curve.knots) if x_changed else curve.knots)
            design = _build_spline_design_matrix(np.asarray(fitted_spline.knots), np.asarray(x))
            if np.linalg.matrix_rank(design) < len(fitted_spline.knots):
                raise ValueError(
                    "Include measurements across the spline's knot range to determine its curve."
                )
            candidate.curve_data_ = fitted_spline
        elif isinstance(curve, structs.AkimaFitData):
            candidate.curve_data_ = akima_fit(x, y)
        else:
            raise ValueError("This calibration curve cannot be recalculated.")

    fitted = candidate.curve_data_
    values = (
        fitted.coefficients
        if isinstance(fitted, structs.PolyFitCoefficients)
        else fitted.knots + [value for row in fitted.coefficients for value in row]
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("Unable to calculate a finite calibration curve from these measurements.")
    return candidate
