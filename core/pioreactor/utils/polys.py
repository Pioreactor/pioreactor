# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Sequence

import numpy as np


def _to_pyfloat(seq: list[float]) -> list[float]:
    # we have trouble serializing numpy floats
    return [float(_) for _ in seq]


def poly_fit(
    x: Sequence[float],
    y: Sequence[float],
    degree: int,
    weights: Sequence[float] | None = None,
) -> list[float]:
    if degree < 0:
        raise ValueError("degree must be >= 0.")

    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size < degree + 1:
        raise ValueError("Not enough data points for requested degree.")

    if weights is None:
        weight_values = np.ones_like(x_values)
    else:
        weight_values = np.asarray(weights, dtype=float)
        if weight_values.size != x_values.size:
            raise ValueError("weights must match the length of x and y.")
        if np.any(weight_values < 0):
            raise ValueError("weights must be non-negative.")

    coefs = np.polyfit(x_values, y_values, deg=degree, w=weight_values)
    return _to_pyfloat(coefs.tolist())


def poly_eval(poly_data: list[float], x: float) -> float:
    return np.polyval(poly_data, x)


def poly_solve(poly_data: list[float], y: float) -> list[float]:
    if len(poly_data) == 0:
        raise ValueError("poly_data must not be empty.")

    coef_shift = np.zeros_like(poly_data, dtype=float)
    coef_shift[-1] = y
    solve_for_poly = np.asarray(poly_data, dtype=float) - coef_shift
    roots_ = np.roots(solve_for_poly).tolist()
    return sorted([float(np.real(r)) for r in roots_ if (abs(np.imag(r)) < 1e-10)])
