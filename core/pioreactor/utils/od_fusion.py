# -*- coding: utf-8 -*-
from math import exp
from math import isfinite
from math import log
from math import log10
from statistics import median
from typing import Iterable
from typing import Mapping

from msgspec import Struct
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.utils.splines import spline_eval
from pioreactor.utils.splines import spline_eval_derivative
from pioreactor.utils.splines import spline_fit
from pioreactor.utils.splines import spline_fit_interpolating

# Model: we fuse three angle-dependent channels into one scalar concentration estimate.
# Each channel is treated as a noisy sensor of concentration with:
#   logy_i = mu_i(logc) + eps_i(logc)
# where:
#   logc = log10(concentration)
#   logy_i = log(od_reading at angle i)
#   mu_i(logc) is a forward calibration curve (natural spline fit to medians)
#   eps_i has scale sigma_i(logc) (robustly estimated from replicate residuals)
#
# Fusion is MAP / maximum-likelihood estimation:
#   logc_hat = argmin_logc sum_i [ 0.5*(r_i/sigma_i)^2 + log(sigma_i) ]
# where:
#   r_i = logy_obs_i - mu_i(logc)
#
# This is "soft weighting" not switching:
# - Channels become less influential where sigma_i is large (noisy/artifacty),
#   or where mu_i is flat (many logc explain the same logy, so the likelihood is broad).
FUSION_ANGLES: tuple[pt.PdAngle, ...] = ("45", "90", "135")


class FusionFitResult(Struct, frozen=True):
    # mu_splines[angle] stores the forward mean model mu_angle(logc) in log(signal) space.
    mu_splines: dict[pt.PdAngle, structs.SplineFitData]

    # sigma_splines_log[angle] stores a model for log(sigma_angle(logc)).
    # We spline the log(sigma) so sigma stays positive after exp().
    sigma_splines_log: dict[pt.PdAngle, structs.SplineFitData]

    # Bounds on logc used during inversion. This prevents extrapolation.
    min_logc: float
    max_logc: float

    # Lower bound on sigma in log(signal) units, to avoid zero or unrealistically small variance.
    # This acts like an "electronics + model mismatch" floor.
    sigma_floor: float

    # Optional diagnostics / plotting payload. Stores per-angle median points.
    recorded_data: dict[str, object]


def _golden_section_minimize(
    fn,
    lower: float,
    upper: float,
    *,
    max_iter: int = 64,
    tol: float = 1e-6,
) -> float:
    # 1D bounded minimizer for the negative log-likelihood.
    # This assumes the objective is reasonably unimodal in practice; if it is multimodal,
    # golden-section may converge to a local minimum. For your current "keep it simple"
    # version, this is fine and fast.
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


def _global_minimize(
    fn,
    lower: float,
    upper: float,
    *,
    grid_points: int = 256,
    refine_points: int = 4,
) -> float:
    # Multi-modal friendly minimizer:
    # 1) coarse grid scan to find candidate minima,
    # 2) refine with bounded golden-section around the best few.
    if upper <= lower:
        return float(lower)

    grid_points = max(8, int(grid_points))
    step = (upper - lower) / (grid_points - 1)
    grid = [lower + i * step for i in range(grid_points)]
    values = [fn(x) for x in grid]

    # Collect local minima (including edges).
    candidates: list[tuple[float, float]] = []
    for i, x in enumerate(grid):
        val = values[i]
        left = values[i - 1] if i > 0 else float("inf")
        right = values[i + 1] if i < grid_points - 1 else float("inf")
        if val <= left and val <= right:
            candidates.append((val, x))

    if not candidates:
        best_index = min(range(len(values)), key=values.__getitem__)
        return grid[best_index]

    candidates.sort(key=lambda pair: pair[0])
    best_candidates = candidates[: max(1, refine_points)]

    best_x = best_candidates[0][1]
    best_val = fn(best_x)
    for _, center in best_candidates:
        left = max(lower, center - step)
        right = min(upper, center + step)
        refined = _golden_section_minimize(fn, left, right)
        refined_val = fn(refined)
        if refined_val < best_val:
            best_val = refined_val
            best_x = refined

    return float(best_x)


def fit_fusion_model(
    records: Iterable[tuple[pt.PdAngle, float, float]],
    *,
    sigma_floor: float = 0.04,
    angles: tuple[pt.PdAngle, ...] = FUSION_ANGLES,
) -> FusionFitResult:
    # Input records are (angle, concentration, reading).
    # concentration is "true" calibration concentration.
    # reading is a normalized channel reading (already divided by reference PD).
    #
    # We fit in log space for stability across decades of concentration and to make variance
    # more homogeneous:
    #   logc = log10(concentration)
    #   logy = log(reading)
    #
    # Forward curve per angle:
    #   mu_angle(logc) = spline_fit( logc -> median(logy at that logc) )
    #
    # Reliability per angle:
    #   residuals r = logy - mu_angle(logc)
    #   sigma_angle(logc) estimated via MAD(residuals at that logc)
    #   then spline_fit(logc -> log(sigma)) to get sigma at arbitrary logc.
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
    recorded_data: dict[str, object] = {"by_angle": {}}

    for angle in angles:
        records_for_angle = by_angle.get(angle, [])
        if not records_for_angle:
            raise ValueError(f"Missing fusion calibration data for angle {angle}.")

        # Group by concentration level (in log space). This assumes the calibration concentrations
        # are exact repeated levels.
        grouped: dict[float, list[float]] = {}
        for logc, logy in records_for_angle:
            grouped.setdefault(logc, []).append(logy)
            logc_values.append(logc)

        # Fit mu: use median at each concentration to be robust to bubbles/artifacts.
        med_points = sorted((lc, median(values)) for lc, values in grouped.items())
        if len(med_points) < 4:
            raise ValueError(f"Need >=4 unique concentration levels to fit fusion spline for angle {angle}.")

        x_vals = [lc for lc, _ in med_points]
        y_vals = [ly for _, ly in med_points]

        # mu_splines[angle] is forward model mu_angle(logc) in log(signal) space.
        # Your spline_fit likely produces a natural cubic spline or equivalent depending on implementation.
        mu_splines[angle] = spline_fit_interpolating(x_vals, y_vals)

        cast_by_angle = recorded_data["by_angle"]
        if isinstance(cast_by_angle, dict):
            cast_by_angle[angle] = {"x": x_vals, "y": y_vals}

        # Compute residuals at calibration points: r = logy - mu(logc)
        # These residuals contain measurement noise + unmodeled effects.
        residuals_by_logc: dict[float, list[float]] = {}
        for logc, logy in records_for_angle:
            mu = spline_eval(mu_splines[angle], logc)
            residuals_by_logc.setdefault(logc, []).append(logy - mu)

        # Estimate sigma per concentration level using MAD (robust scale).
        # sigma is in log(signal) units.
        sig_points: list[tuple[float, float]] = []
        for logc, residuals in residuals_by_logc.items():
            median_resid = median(residuals)
            mad = median([abs(r - median_resid) for r in residuals])

            # 1.4826 * MAD approximates std for Gaussian residuals.
            # sigma_floor prevents pathological overconfidence.
            sigma = max(1.4826 * mad, sigma_floor)
            sig_points.append((logc, sigma))

        # Fit a spline to log(sigma) vs logc, so sigma(logc) is smooth and positive.
        sig_points.sort(key=lambda pair: pair[0])
        sig_x = [lc for lc, _ in sig_points]
        sig_y = [log(sig) for _, sig in sig_points]
        sigma_splines_log[angle] = spline_fit(sig_x, sig_y, knots="auto")

    # Inversion bounds: restrict to the calibrated logc range.
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
    estimator: structs.ODFusionEstimator,
    angle: pt.PdAngle,
    logc: float,
) -> float:
    # sigma(logc) = exp( spline_eval( log_sigma_spline, logc ) )
    # Floor applied to avoid overconfident likelihood terms.
    sigma_log = spline_eval(estimator.sigma_splines_log[angle], logc)
    sigma = exp(sigma_log)
    return max(sigma, estimator.sigma_floor)


def compute_fused_od(
    estimator: structs.ODFusionEstimator,
    readings_by_angle: Mapping[pt.PdAngle, float],
) -> float:
    # Inputs: one measurement per angle (already normalized).
    # We fuse them by solving for concentration that minimizes total negative log-likelihood.

    for angle in estimator.angles:
        if angle not in readings_by_angle:
            raise ValueError(f"Missing fusion reading for angle {angle}.")

    # Transform observations to log(signal) space to match the mu and sigma models.
    log_obs: dict[pt.PdAngle, float] = {}
    for angle in estimator.angles:
        reading = readings_by_angle[angle]
        log_obs[angle] = log(max(float(reading), 1e-12))

    slope_floor = 0.05

    def _angle_noise_scale(angle: pt.PdAngle, logc: float) -> float:
        # Gentle prior: at low concentrations, 135 tends to be the cleanest,
        # but avoid over-weighting a single angle across instruments.
        low_logc = -2.5
        high_logc = -0.1
        if logc <= low_logc:
            t = 1.0
        elif logc >= high_logc:
            t = 0.0
        else:
            t = (high_logc - logc) / (high_logc - low_logc)
        low_scales = {"135": 0.04, "90": 4.0, "45": 10.0}
        scale = low_scales[angle]
        return 1.0 * (1.0 - t) + scale * t

    def nll(logc: float) -> float:
        # Negative log-likelihood assuming independent Gaussian residuals per angle:
        #   logy_obs = mu_angle(logc) + Normal(0, sigma_angle(logc)^2)
        #
        # Sum of per-angle NLL (dropping additive constants):
        #   0.5*(r/sigma)^2 + log(sigma)
        #
        # We use a pseudo-Huber penalty on the normalized residual to reduce
        # the impact of occasional bubbles/artifacts without changing small-error behavior.
        huber_delta = 1.0
        total = 0.0
        for angle in estimator.angles:
            mu = spline_eval(estimator.mu_splines[angle], logc)
            sigma = _sigma_from_model(estimator, angle, logc)
            slope = abs(spline_eval_derivative(estimator.mu_splines[angle], logc))
            sigma_eff = sigma / max(slope, slope_floor)
            sigma_eff *= _angle_noise_scale(angle, logc)
            residual = log_obs[angle] - mu
            r = residual / sigma_eff
            huber_term = huber_delta**2 * ((1.0 + (r / huber_delta) ** 2) ** 0.5 - 1.0)
            total += huber_term + log(sigma_eff)
        return total

    # MAP / ML estimate:
    #   logc_hat = argmin nll(logc) over [min_logc, max_logc]
    logc_hat = _global_minimize(nll, estimator.min_logc, estimator.max_logc)

    # Return concentration estimate in linear units (OD proxy).
    c_hat = 10**logc_hat

    if not isfinite(c_hat):
        raise ValueError("Fusion model produced non-finite OD estimate.")

    return float(c_hat)
