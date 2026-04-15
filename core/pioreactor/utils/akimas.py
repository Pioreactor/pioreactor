# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
from typing import Sequence

from pioreactor import structs
from pioreactor.utils.piecewise_cubics import interval_index
from pioreactor.utils.piecewise_cubics import parse_piecewise_cubic_data
from pioreactor.utils.piecewise_cubics import solve_piecewise_cubic
from pioreactor.utils.piecewise_cubics import to_pyfloat


def akima_fit(x: Sequence[float], y: Sequence[float]) -> structs.AkimaFitData:
    import numpy as np

    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size < 2:
        raise ValueError("At least two data points are required.")

    order = np.argsort(x_values)
    x_sorted = x_values[order]
    y_sorted = y_values[order]

    grouped: dict[float, list[float]] = {}
    for x_value, y_value in zip(x_sorted.tolist(), y_sorted.tolist()):
        grouped.setdefault(float(x_value), []).append(float(y_value))

    unique_x = sorted(grouped.keys())
    if len(unique_x) < 2:
        raise ValueError("At least two unique x values are required.")

    x_sorted = np.asarray(unique_x, dtype=float)
    y_sorted = np.asarray(
        [sum(grouped[x_value]) / len(grouped[x_value]) for x_value in unique_x], dtype=float
    )

    derivatives = _akima_derivatives(x_sorted, y_sorted)
    coefficients = _akima_coefficients(x_sorted, y_sorted, derivatives)

    return structs.AkimaFitData(
        knots=to_pyfloat(x_sorted.tolist()),
        coefficients=[to_pyfloat(coeff.tolist()) for coeff in coefficients],
    )


def akima_eval(akima_data: structs.AkimaFitData, x: float) -> float:
    knots, coefficients = _parse_akima_data(akima_data)
    index = interval_index(knots, x)
    u = x - knots[index]
    a, b, c, d = coefficients[index]
    return float(a + b * u + c * u**2 + d * u**3)


def akima_eval_derivative(akima_data: structs.AkimaFitData, x: float) -> float:
    knots, coefficients = _parse_akima_data(akima_data)
    index = interval_index(knots, x)
    u = x - knots[index]
    _, b, c, d = coefficients[index]
    return float(b + 2.0 * c * u + 3.0 * d * u**2)


def akima_solve(akima_data: structs.AkimaFitData, y: float) -> list[float]:
    knots, coefficients = _parse_akima_data(akima_data)
    return solve_piecewise_cubic(knots, coefficients, y)


def _akima_derivatives(x_values: Any, y_values: Any) -> Any:
    import numpy as np

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
    x_values: Any,
    y_values: Any,
    derivatives: Any,
) -> Any:
    import numpy as np

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


def _parse_akima_data(akima_data: structs.AkimaFitData) -> tuple[Any, Any]:
    return parse_piecewise_cubic_data(akima_data, structs.AkimaFitData, "akima_data")
