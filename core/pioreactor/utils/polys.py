# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Sequence

import numpy as np
from pioreactor import types as pt


def _to_pyfloat(seq: list[float]) -> list[float]:
    # we have trouble serializing numpy floats
    return [float(_) for _ in seq]


def poly_fit(
    x: Sequence[float],
    y: Sequence[float],
    degree: int | str | None = "auto",
    weights: Sequence[float] | None = None,
) -> pt.PolyFitCoefficients:
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size == 0:
        raise ValueError("x and y must not be empty.")

    if weights is None:
        weight_values = np.ones_like(x_values)
    else:
        weight_values = np.asarray(weights, dtype=float)
        if weight_values.size != x_values.size:
            raise ValueError("weights must match the length of x and y.")
        if np.any(weight_values < 0):
            raise ValueError("weights must be non-negative.")

    selected_degree = _normalize_degree(degree, x_values, y_values, weight_values)

    if selected_degree < 0:
        raise ValueError("degree must be >= 0.")
    if x_values.size < selected_degree + 1:
        raise ValueError("Not enough data points for requested degree.")

    coefs = np.polyfit(x_values, y_values, deg=selected_degree, w=weight_values)
    return _to_pyfloat(coefs.tolist())


def poly_eval(poly_data: pt.PolyFitCoefficients, x: float) -> float:
    return float(np.polyval(poly_data, x))


def poly_solve(poly_data: pt.PolyFitCoefficients, y: float) -> list[float]:
    if len(poly_data) == 0:
        raise ValueError("poly_data must not be empty.")

    coef_shift = np.zeros_like(poly_data, dtype=float)
    coef_shift[-1] = y
    solve_for_poly = np.asarray(poly_data, dtype=float) - coef_shift
    roots_ = np.roots(solve_for_poly).tolist()
    return sorted([float(np.real(r)) for r in roots_ if (abs(np.imag(r)) < 1e-10)])


def _aicc_score(weighted_sse: float, n_obs: int, n_params: int) -> float:
    if n_obs <= n_params + 1:
        return float("inf")
    sse = max(weighted_sse, np.finfo(float).tiny)
    correction = (2 * n_params * (n_params + 1)) / (n_obs - n_params - 1)
    return n_obs * np.log(sse / n_obs) + 2 * n_params + correction


def _normalize_degree(
    degree: int | str | None,
    x_values: np.ndarray,
    y_values: np.ndarray,
    weight_values: np.ndarray,
) -> int:
    if degree is None or degree == "auto":
        return _auto_select_degree(x_values, y_values, weight_values)
    if isinstance(degree, str):
        raise ValueError('degree must be an int or "auto".')
    return int(degree)


def _auto_select_degree(
    x_values: np.ndarray,
    y_values: np.ndarray,
    weight_values: np.ndarray,
    *,
    max_degree: int | None = None,
) -> int:
    n_obs = x_values.size
    unique_x = np.unique(x_values).size

    if max_degree is None:
        max_degree = min(5, n_obs - 1)
    max_degree = min(max_degree, unique_x - 1)
    max_degree = max(0, max_degree)

    best_score = float("inf")
    best_degree: int | None = None

    for degree in range(0, max_degree + 1):
        try:
            coefs = np.polyfit(x_values, y_values, deg=degree, w=weight_values)
        except np.linalg.LinAlgError:
            continue

        y_pred = np.polyval(coefs, x_values)
        residual = y_values - y_pred
        weighted_sse = float(np.sum(weight_values * residual**2))
        score = _aicc_score(weighted_sse, n_obs, degree + 1)
        if score < best_score:
            best_score = score
            best_degree = degree

    if best_degree is None:
        return 0
    return best_degree
