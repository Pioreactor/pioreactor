# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Iterable
from typing import Sequence

import numpy as np
from pioreactor import structs


def _to_pyfloat(seq: list[float]) -> list[float]:
    return [float(value) for value in seq]


def akima_fit(x: Sequence[float], y: Sequence[float]) -> structs.AkimaFitData:
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size < 2:
        raise ValueError("At least two data points are required.")

    order = np.argsort(x_values)
    x_sorted = x_values[order]
    y_sorted = y_values[order]

    if np.any(np.diff(x_sorted) <= 0):
        raise ValueError("x values must be strictly increasing for Akima interpolation.")

    derivatives = _akima_derivatives(x_sorted, y_sorted)
    coefficients = _akima_coefficients(x_sorted, y_sorted, derivatives)

    return structs.AkimaFitData(
        knots=_to_pyfloat(x_sorted.tolist()),
        coefficients=[_to_pyfloat(coeff.tolist()) for coeff in coefficients],
    )


def akima_eval(akima_data: structs.AkimaFitData, x: float) -> float:
    knots, coefficients = _parse_akima_data(akima_data)
    index = _interval_index(knots, x)
    u = x - knots[index]
    a, b, c, d = coefficients[index]
    return float(a + b * u + c * u**2 + d * u**3)


def akima_eval_derivative(akima_data: structs.AkimaFitData, x: float) -> float:
    knots, coefficients = _parse_akima_data(akima_data)
    index = _interval_index(knots, x)
    u = x - knots[index]
    _, b, c, d = coefficients[index]
    return float(b + 2.0 * c * u + 3.0 * d * u**2)


def akima_solve(akima_data: structs.AkimaFitData, y: float) -> list[float]:
    knots, coefficients = _parse_akima_data(akima_data)
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

    return _to_pyfloat(_unique_sorted(solutions))


def _akima_derivatives(x_values: np.ndarray, y_values: np.ndarray) -> np.ndarray:
    n = x_values.size
    slopes = np.diff(y_values) / np.diff(x_values)

    extended = np.empty(n + 3, dtype=float)
    extended[2 : n + 1] = slopes

    extended[1] = 2.0 * extended[2] - extended[3]
    extended[0] = 2.0 * extended[1] - extended[2]
    extended[n + 1] = 2.0 * extended[n] - extended[n - 1]
    extended[n + 2] = 2.0 * extended[n + 1] - extended[n]

    derivatives = np.empty(n, dtype=float)
    for i in range(n):
        w1 = abs(extended[i + 3] - extended[i + 2])
        w2 = abs(extended[i + 1] - extended[i])
        if w1 + w2 > 0:
            derivatives[i] = (w1 * extended[i + 1] + w2 * extended[i + 2]) / (w1 + w2)
        else:
            derivatives[i] = 0.5 * (extended[i + 1] + extended[i + 2])

    return derivatives


def _akima_coefficients(
    x_values: np.ndarray,
    y_values: np.ndarray,
    derivatives: np.ndarray,
) -> np.ndarray:
    n = x_values.size
    coefficients = np.zeros((n - 1, 4), dtype=float)

    for i in range(n - 1):
        h = x_values[i + 1] - x_values[i]
        if h <= 0:
            raise ValueError("x values must be strictly increasing.")
        dy = y_values[i + 1] - y_values[i]
        a = y_values[i]
        b = derivatives[i]
        c = (3.0 * dy / h - 2.0 * derivatives[i] - derivatives[i + 1]) / h
        d = (2.0 * (-dy) / h + derivatives[i] + derivatives[i + 1]) / (h**2)
        coefficients[i] = [a, b, c, d]

    return coefficients


def _interval_index(knots: np.ndarray, x: float) -> int:
    idx = int(np.searchsorted(knots, x, side="right") - 1)
    if idx < 0:
        return 0
    if idx >= len(knots) - 1:
        return len(knots) - 2
    return idx


def _parse_akima_data(akima_data: structs.AkimaFitData) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(akima_data, structs.AkimaFitData):
        raise ValueError("akima_data must be an AkimaFitData struct.")

    knots = np.asarray(akima_data.knots, dtype=float)
    coefficients = np.asarray(akima_data.coefficients, dtype=float)

    if knots.ndim != 1 or coefficients.ndim != 2 or coefficients.shape[1] != 4:
        raise ValueError("Invalid akima_data format.")
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
    real_roots: list[float] = []
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
