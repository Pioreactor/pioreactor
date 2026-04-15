# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
from typing import Iterable
from typing import Sequence


def to_pyfloat(seq: list[float]) -> list[float]:
    return [float(value) for value in seq]


def interval_index(knots: Any, x: float) -> int:
    import numpy as np

    idx = int(np.searchsorted(knots, x, side="right") - 1)
    if idx < 0:
        return 0
    if idx >= len(knots) - 1:
        return len(knots) - 2
    return idx


def parse_piecewise_cubic_data(
    piecewise_data: Any,
    expected_type: type[Any],
    data_name: str,
) -> tuple[Any, Any]:
    import numpy as np

    if not isinstance(piecewise_data, expected_type):
        raise ValueError(f"{data_name} must be a {expected_type.__name__} struct.")

    knots = np.asarray(piecewise_data.knots, dtype=float)
    coefficients = np.asarray(piecewise_data.coefficients, dtype=float)

    if knots.ndim != 1 or coefficients.ndim != 2 or coefficients.shape[1] != 4:
        raise ValueError(f"Invalid {data_name} format.")
    if knots.size != coefficients.shape[0] + 1:
        raise ValueError("Coefficient count must be len(knots) - 1.")
    if np.any(np.diff(knots) <= 0):
        raise ValueError("Knots must be strictly increasing.")

    return knots, coefficients


def solve_piecewise_cubic(knots: Any, coefficients: Any, y: float) -> list[float]:
    import numpy as np

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

    return to_pyfloat(_unique_sorted(solutions))


def _real_roots_in_interval(coefficients: Iterable[float], start: float, end: float) -> list[float]:
    import numpy as np

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


def _trim_leading_zeros(values: Any) -> Any:
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
