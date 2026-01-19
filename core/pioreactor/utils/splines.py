# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Iterable
from typing import Sequence

import numpy as np


def spline_fit(
    x: Sequence[float],
    y: Sequence[float],
    knots: int | Sequence[float],
    weights: Sequence[float] | None = None,
) -> list:
    """
    Fit a natural cubic regression spline.

    Parameters
    ----------
    x, y
        Observations.
    knots
        Either the number of knots to use (including boundaries) or explicit knot positions.
    weights
        Optional weights for each observation.

    Returns
    -------
    list
        A list representation containing knots and per-interval coefficients.
    """
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size < 2:
        raise ValueError("At least two data points are required.")

    if np.allclose(x_values, x_values[0]):
        raise ValueError("x values must not all be the same.")

    knot_positions = _normalize_knots(x_values, knots)
    if len(knot_positions) < 2:
        raise ValueError("At least two knots are required.")

    if weights is None:
        weight_values = np.ones_like(x_values)
    else:
        weight_values = np.asarray(weights, dtype=float)
        if weight_values.size != x_values.size:
            raise ValueError("weights must match the length of x and y.")
        if np.any(weight_values < 0):
            raise ValueError("weights must be non-negative.")

    design_matrix = _build_spline_design_matrix(knot_positions, x_values)
    weighted_design = design_matrix * np.sqrt(weight_values)[:, None]
    weighted_y = y_values * np.sqrt(weight_values)

    knot_values, *_ = np.linalg.lstsq(weighted_design, weighted_y, rcond=None)
    coefficients = _natural_cubic_spline_coefficients(knot_positions, knot_values)

    return [knot_positions.tolist(), [coeff.tolist() for coeff in coefficients]]


def spline_eval(spline_data: list, x: float) -> float:
    """Evaluate a spline produced by spline_fit at a point."""
    knots, coefficients = _parse_spline_data(spline_data)
    index = _interval_index(knots, x)
    u = x - knots[index]
    a, b, c, d = coefficients[index]
    return a + b * u + c * u**2 + d * u**3


def spline_solve(spline_data: list, y: float) -> list[float]:
    """Solve spline(x) == y for all real solutions."""
    knots, coefficients = _parse_spline_data(spline_data)
    solutions: list[float] = []
    last_index = len(coefficients) - 1

    for index, (a, b, c, d) in enumerate(coefficients):
        h = knots[index + 1] - knots[index]
        if h <= 0:
            raise ValueError("Knots must be strictly increasing.")

        if last_index == 0:
            lower, upper = -np.inf, np.inf
        elif index == 0:
            lower, upper = -np.inf, h
        elif index == last_index:
            lower, upper = 0.0, np.inf
        else:
            lower, upper = 0.0, h

        roots = _real_roots_in_interval([d, c, b, a - y], lower, upper)
        for root in roots:
            solutions.append(knots[index] + root)

    return _unique_sorted(solutions)


def _interval_index(knots: np.ndarray, x: float) -> int:
    idx = int(np.searchsorted(knots, x, side="right") - 1)
    if idx < 0:
        return 0
    if idx >= len(knots) - 1:
        return len(knots) - 2
    return idx


def _normalize_knots(x_values: np.ndarray, knots: int | Sequence[float]) -> np.ndarray:
    x_min = float(np.min(x_values))
    x_max = float(np.max(x_values))

    if isinstance(knots, int):
        if knots < 2:
            raise ValueError("knots must be >= 2.")
        quantiles = np.linspace(0.0, 1.0, knots)
        knot_positions = np.quantile(x_values, quantiles)
    else:
        knot_positions = np.array(list(knots), dtype=float)
        if knot_positions.size == 0:
            raise ValueError("knots must not be empty.")
        if knot_positions.min() > x_min:
            knot_positions = np.append(knot_positions, x_min)
        if knot_positions.max() < x_max:
            knot_positions = np.append(knot_positions, x_max)

    knot_positions = np.unique(np.sort(knot_positions))
    if knot_positions.size < 2:
        raise ValueError("knots must contain at least two unique values.")
    return knot_positions


def _build_spline_design_matrix(knots: np.ndarray, x_values: np.ndarray) -> np.ndarray:
    n = x_values.size
    m = knots.size
    design = np.zeros((n, m), dtype=float)
    for idx in range(m):
        knot_values = np.zeros(m, dtype=float)
        knot_values[idx] = 1.0
        coeffs = _natural_cubic_spline_coefficients(knots, knot_values)
        design[:, idx] = _evaluate_coefficients(knots, coeffs, x_values)
    return design


def _evaluate_coefficients(knots: np.ndarray, coefficients: np.ndarray, x_values: np.ndarray) -> np.ndarray:
    results = np.empty_like(x_values, dtype=float)
    for i, x in enumerate(x_values):
        index = _interval_index(knots, float(x))
        u = x - knots[index]
        a, b, c, d = coefficients[index]
        results[i] = a + b * u + c * u**2 + d * u**3
    return results


def _natural_cubic_spline_coefficients(knots: np.ndarray, values: np.ndarray) -> np.ndarray:
    n = knots.size
    if values.size != n:
        raise ValueError("values must match knot count.")

    h = np.diff(knots)
    if np.any(h <= 0):
        raise ValueError("Knots must be strictly increasing.")

    if n == 2:
        m = np.array([0.0, 0.0])
    else:
        matrix = np.zeros((n - 2, n - 2), dtype=float)
        rhs = np.zeros(n - 2, dtype=float)

        for i in range(1, n - 1):
            h_prev = h[i - 1]
            h_next = h[i]
            row = i - 1
            if row - 1 >= 0:
                matrix[row, row - 1] = h_prev
            matrix[row, row] = 2.0 * (h_prev + h_next)
            if row + 1 <= n - 3:
                matrix[row, row + 1] = h_next
            rhs[row] = 6.0 * ((values[i + 1] - values[i]) / h_next - (values[i] - values[i - 1]) / h_prev)

        inner_m = np.linalg.solve(matrix, rhs)
        m = np.zeros(n, dtype=float)
        m[1:-1] = inner_m

    coefficients = np.zeros((n - 1, 4), dtype=float)
    for i in range(n - 1):
        h_i = h[i]
        a = values[i]
        b = (values[i + 1] - values[i]) / h_i - h_i * (2.0 * m[i] + m[i + 1]) / 6.0
        c = m[i] / 2.0
        d = (m[i + 1] - m[i]) / (6.0 * h_i)
        coefficients[i] = [a, b, c, d]

    return coefficients


def _parse_spline_data(spline_data: list) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(spline_data, list) or len(spline_data) != 2:
        raise ValueError("spline_data must be [knots, coefficients].")

    knots = np.asarray(spline_data[0], dtype=float)
    coefficients = np.asarray(spline_data[1], dtype=float)

    if knots.ndim != 1 or coefficients.ndim != 2 or coefficients.shape[1] != 4:
        raise ValueError("Invalid spline_data format.")
    if knots.size != coefficients.shape[0] + 1:
        raise ValueError("Coefficient count must be len(knots) - 1.")
    if np.any(np.diff(knots) <= 0):
        raise ValueError("Knots must be strictly increasing.")

    return knots, coefficients


def _real_roots_in_interval(coefficients: Iterable[float], start: float, end: float) -> list[float]:
    coeff_array = np.array(list(coefficients), dtype=float)
    coeff_array = _trim_leading_zeros(coeff_array)
    if coeff_array.size == 0:
        if np.isfinite(start) and np.isfinite(end):
            return [start, end]
        return []

    roots = np.roots(coeff_array)
    real_roots = []
    for root in roots:
        if abs(root.imag) > 1e-9:
            continue
        value = float(root.real)
        lower_ok = value >= start - 1e-9 if np.isfinite(start) else True
        upper_ok = value <= end + 1e-9 if np.isfinite(end) else True
        if lower_ok and upper_ok:
            real_roots.append(min(max(value, start), end))

    return real_roots


def _trim_leading_zeros(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    idx = 0
    while idx < values.size and abs(values[idx]) < 1e-12:
        idx += 1
    return values[idx:]


def _unique_sorted(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    unique_values = [sorted_values[0]]
    for value in sorted_values[1:]:
        if abs(value - unique_values[-1]) > 1e-7:
            unique_values.append(value)
    return unique_values
