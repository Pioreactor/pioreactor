# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
from typing import Sequence

from pioreactor import structs
from pioreactor.utils.piecewise_cubics import interval_index
from pioreactor.utils.piecewise_cubics import parse_piecewise_cubic_data
from pioreactor.utils.piecewise_cubics import solve_piecewise_cubic
from pioreactor.utils.piecewise_cubics import to_pyfloat


def spline_fit(
    x: Sequence[float],
    y: Sequence[float],
    knots: int | Sequence[float] | str | None = "auto",
    weights: Sequence[float] | None = None,
) -> structs.SplineFitData:
    import numpy as np

    """
    Fit a natural cubic regression spline.

    Parameters
    ----------
    x, y
        Observations.
    knots
        Either the number of knots to use (including boundaries), explicit knot positions, or "auto".
        When "auto" (default), knot count is selected by AICc over a small candidate range.
    weights
        Optional weights for each observation.

    Returns
    -------
    structs.SplineFitData
        A struct representation containing knots and per-interval coefficients.
    """
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.size != y_values.size:
        raise ValueError("x and y must have the same length.")
    if x_values.size < 2:
        raise ValueError("At least two data points are required.")

    if np.allclose(x_values, x_values[0]):
        raise ValueError("x values must not all be the same.")

    if weights is None:
        weight_values = np.ones_like(x_values)
    else:
        weight_values = np.asarray(weights, dtype=float)
        if weight_values.size != x_values.size:
            raise ValueError("weights must match the length of x and y.")
        if np.any(weight_values < 0):
            raise ValueError("weights must be non-negative.")

    if knots is None or knots == "auto":
        knot_positions = _auto_select_knots(x_values, y_values, weight_values)
    elif isinstance(knots, str):
        raise ValueError('knots must be an int, a sequence of floats, or "auto".')
    else:
        knot_positions = _normalize_knots(x_values, knots)
    if len(knot_positions) < 2:
        raise ValueError("At least two knots are required.")

    knot_values, _ = _fit_knot_values(knot_positions, x_values, y_values, weight_values)
    coefficients = _natural_cubic_spline_coefficients(knot_positions, knot_values)

    return structs.SplineFitData(
        knots=to_pyfloat(knot_positions.tolist()),
        coefficients=[to_pyfloat(coeff.tolist()) for coeff in coefficients],
    )


def spline_fit_interpolating(x: Sequence[float], y: Sequence[float]) -> structs.SplineFitData:
    import numpy as np

    """
    Fit a natural cubic spline that interpolates every data point.

    Parameters
    ----------
    x, y
        Observations. x values must be strictly increasing after sorting.
    """
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
        raise ValueError("x values must be strictly increasing for interpolation.")

    coefficients = _natural_cubic_spline_coefficients(x_sorted, y_sorted)

    return structs.SplineFitData(
        knots=to_pyfloat(x_sorted.tolist()),
        coefficients=[to_pyfloat(coeff.tolist()) for coeff in coefficients],
    )


def spline_eval(spline_data: structs.SplineFitData, x: float) -> float:
    """Evaluate a spline produced by spline_fit at a point."""
    knots, coefficients = _parse_spline_data(spline_data)
    index = interval_index(knots, x)
    u = x - knots[index]
    a, b, c, d = coefficients[index]
    return float(a + b * u + c * u**2 + d * u**3)


def spline_eval_derivative(spline_data: structs.SplineFitData, x: float) -> float:
    """Evaluate the first derivative of a spline at a point."""
    knots, coefficients = _parse_spline_data(spline_data)
    index = interval_index(knots, x)
    u = x - knots[index]
    _, b, c, d = coefficients[index]
    return float(b + 2.0 * c * u + 3.0 * d * u**2)


def spline_solve(spline_data: structs.SplineFitData, y: float) -> list[float]:
    """Solve spline(x) == y for all real solutions."""
    knots, coefficients = _parse_spline_data(spline_data)
    return solve_piecewise_cubic(knots, coefficients, y)


def _normalize_knots(x_values: Any, knots: int | Sequence[float]) -> Any:
    import numpy as np

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


def _fit_knot_values(
    knot_positions: Any,
    x_values: Any,
    y_values: Any,
    weight_values: Any,
) -> tuple[Any, Any]:
    import numpy as np

    design_matrix = _build_spline_design_matrix(knot_positions, x_values)
    sqrt_weights = np.sqrt(weight_values)
    weighted_design = design_matrix * sqrt_weights[:, None]
    weighted_y = y_values * sqrt_weights
    knot_values, *_ = np.linalg.lstsq(weighted_design, weighted_y, rcond=None)
    return knot_values, design_matrix


def _aicc_score(weighted_sse: float, n_obs: int, n_params: int) -> float:
    import numpy as np

    if n_obs <= n_params + 1:
        return float("inf")
    sse = max(weighted_sse, np.finfo(float).tiny)
    correction = (2 * n_params * (n_params + 1)) / (n_obs - n_params - 1)
    return n_obs * np.log(sse / n_obs) + 2 * n_params + correction


def _auto_select_knots(
    x_values: Any,
    y_values: Any,
    weight_values: Any,
    *,
    max_knots: int | None = None,
) -> Any:
    import numpy as np

    n_obs = x_values.size
    unique_x = np.unique(x_values).size
    if max_knots is None:
        max_knots = min(6, n_obs)
    max_knots = min(max_knots, unique_x)
    max_knots = max(2, max_knots)

    best_score = float("inf")
    best_knots: Any | None = None

    for count in range(2, max_knots + 1):
        knot_positions = _normalize_knots(x_values, count)
        knot_values, design_matrix = _fit_knot_values(knot_positions, x_values, y_values, weight_values)
        y_pred = design_matrix @ knot_values
        residual = y_values - y_pred
        weighted_sse = float(np.sum(weight_values * residual**2))
        score = _aicc_score(weighted_sse, n_obs, knot_positions.size)
        if score < best_score:
            best_score = score
            best_knots = knot_positions

    if best_knots is None:
        return _normalize_knots(x_values, 2)
    return best_knots


def _build_spline_design_matrix(knots: Any, x_values: Any) -> Any:
    import numpy as np

    n = x_values.size
    m = knots.size
    design = np.zeros((n, m), dtype=float)
    for idx in range(m):
        knot_values = np.zeros(m, dtype=float)
        knot_values[idx] = 1.0
        coeffs = _natural_cubic_spline_coefficients(knots, knot_values)
        design[:, idx] = _evaluate_coefficients(knots, coeffs, x_values)
    return design


def _evaluate_coefficients(knots: Any, coefficients: Any, x_values: Any) -> Any:
    import numpy as np

    results = np.empty_like(x_values, dtype=float)
    for i, x in enumerate(x_values):
        index = interval_index(knots, float(x))
        u = x - knots[index]
        a, b, c, d = coefficients[index]
        results[i] = a + b * u + c * u**2 + d * u**3
    return results


def _natural_cubic_spline_coefficients(knots: Any, values: Any) -> Any:
    import numpy as np

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


def _parse_spline_data(spline_data: structs.SplineFitData) -> tuple[Any, Any]:
    return parse_piecewise_cubic_data(spline_data, structs.SplineFitData, "spline_data")
