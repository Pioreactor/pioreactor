# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from math import exp
from math import isfinite
from math import log
from math import log10
from statistics import median
from typing import Iterable
from typing import Mapping

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.utils.splines import spline_eval
from pioreactor.utils.splines import spline_fit

FUSION_ANGLES: tuple[pt.PdAngle, ...] = ("45", "90", "135")


@dataclass(frozen=True)
class FusionFitResult:
    mu_splines: dict[pt.PdAngle, structs.SplineFitData]
    sigma_splines_log: dict[pt.PdAngle, structs.SplineFitData]
    min_logc: float
    max_logc: float
    sigma_floor: float
    recorded_data: dict[str, list[float]]


def _golden_section_minimize(
    fn,
    lower: float,
    upper: float,
    *,
    max_iter: int = 64,
    tol: float = 1e-6,
) -> float:
    phi = (1 + 5**0.5) / 2
    inv_phi = 1 / phi
    inv_phi_sq = inv_phi**2

    a = float(lower)
    b = float(upper)
    if b <= a:
        return a

    h = b - a
    if h <= tol:
        return (a + b) / 2

    c = a + inv_phi_sq * h
    d = a + inv_phi * h
    fc = fn(c)
    fd = fn(d)

    for _ in range(max_iter):
        if abs(b - a) <= tol:
            break
        if fc < fd:
            b = d
            d = c
            fd = fc
            h = b - a
            c = a + inv_phi_sq * h
            fc = fn(c)
        else:
            a = c
            c = d
            fc = fd
            h = b - a
            d = a + inv_phi * h
            fd = fn(d)

    return (a + b) / 2


def fit_fusion_model(
    records: Iterable[tuple[pt.PdAngle, float, float]],
    *,
    sigma_floor: float = 0.05,
    angles: tuple[pt.PdAngle, ...] = FUSION_ANGLES,
) -> FusionFitResult:
    by_angle: dict[pt.PdAngle, list[tuple[float, float]]] = {angle: [] for angle in angles}

    for angle, concentration, reading in records:
        if angle not in by_angle:
            continue
        if concentration <= 0:
            continue
        if reading <= 0:
            continue
        logc = log10(concentration)
        logy = log(max(reading, 1e-12))
        by_angle[angle].append((logc, logy))

    if not any(by_angle.values()):
        raise ValueError("No usable fusion calibration records provided.")

    mu_splines: dict[pt.PdAngle, structs.SplineFitData] = {}
    sigma_splines_log: dict[pt.PdAngle, structs.SplineFitData] = {}

    logc_values: list[float] = []
    recorded_data: dict[str, list[float]] = {"x": [], "y": []}

    for angle in angles:
        records_for_angle = by_angle.get(angle, [])
        if not records_for_angle:
            raise ValueError(f"Missing fusion calibration data for angle {angle}.")

        grouped: dict[float, list[float]] = {}
        for logc, logy in records_for_angle:
            grouped.setdefault(logc, []).append(logy)
            logc_values.append(logc)

        med_points = sorted((lc, median(values)) for lc, values in grouped.items())
        if len(med_points) < 4:
            raise ValueError(f"Need >=4 unique concentration levels to fit fusion spline for angle {angle}.")

        x_vals = [lc for lc, _ in med_points]
        y_vals = [ly for _, ly in med_points]
        mu_splines[angle] = spline_fit(x_vals, y_vals, knots="auto")

        if angle == "90":
            recorded_data["x"] = x_vals
            recorded_data["y"] = y_vals

        residuals_by_logc: dict[float, list[float]] = {}
        for logc, logy in records_for_angle:
            mu = spline_eval(mu_splines[angle], logc)
            residuals_by_logc.setdefault(logc, []).append(logy - mu)

        sig_points: list[tuple[float, float]] = []
        for logc, residuals in residuals_by_logc.items():
            median_resid = median(residuals)
            mad = median([abs(r - median_resid) for r in residuals])
            sigma = max(1.4826 * mad, sigma_floor)
            sig_points.append((logc, sigma))

        sig_points.sort(key=lambda pair: pair[0])
        sig_x = [lc for lc, _ in sig_points]
        sig_y = [log(sig) for _, sig in sig_points]
        sigma_splines_log[angle] = spline_fit(sig_x, sig_y, knots="auto")

    min_logc = min(logc_values)
    max_logc = max(logc_values)

    return FusionFitResult(
        mu_splines=mu_splines,
        sigma_splines_log=sigma_splines_log,
        min_logc=min_logc,
        max_logc=max_logc,
        sigma_floor=sigma_floor,
        recorded_data=recorded_data,
    )


def _sigma_from_model(
    calibration: structs.ODFusionCalibration,
    angle: pt.PdAngle,
    logc: float,
) -> float:
    sigma_log = spline_eval(calibration.sigma_splines_log[angle], logc)
    sigma = exp(sigma_log)
    return max(sigma, calibration.sigma_floor)


def compute_fused_od(
    calibration: structs.ODFusionCalibration,
    readings_by_angle: Mapping[pt.PdAngle, float],
    *,
    return_debug: bool = False,
) -> float | dict[str, object]:
    for angle in calibration.angles:
        if angle not in readings_by_angle:
            raise ValueError(f"Missing fusion reading for angle {angle}.")

    log_obs: dict[pt.PdAngle, float] = {}
    for angle in calibration.angles:
        reading = readings_by_angle[angle]
        log_obs[angle] = log(max(float(reading), 1e-12))

    def nll(logc: float) -> float:
        total = 0.0
        for angle in calibration.angles:
            mu = spline_eval(calibration.mu_splines[angle], logc)
            sigma = _sigma_from_model(calibration, angle, logc)
            residual = log_obs[angle] - mu
            total += 0.5 * (residual / sigma) ** 2 + log(sigma)
        return total

    logc_hat = _golden_section_minimize(nll, calibration.min_logc, calibration.max_logc)
    c_hat = 10**logc_hat

    if not isfinite(c_hat):
        raise ValueError("Fusion model produced non-finite OD estimate.")

    if not return_debug:
        return float(c_hat)

    per_angle: dict[str, dict[str, float]] = {}
    for angle in calibration.angles:
        mu = spline_eval(calibration.mu_splines[angle], logc_hat)
        sigma = _sigma_from_model(calibration, angle, logc_hat)
        residual = log_obs[angle] - mu
        per_angle[str(angle)] = {
            "logy_obs": float(log_obs[angle]),
            "logy_pred": float(mu),
            "resid_logy": float(residual),
            "sigma_logy": float(sigma),
        }

    return {
        "logc_hat": float(logc_hat),
        "od_fused": float(c_hat),
        "nll": float(nll(logc_hat)),
        "per_angle": per_angle,
    }
