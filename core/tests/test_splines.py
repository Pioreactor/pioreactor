# -*- coding: utf-8 -*-
from typing import cast

import numpy as np
import pytest
from pioreactor import structs
from pioreactor.utils.splines import spline_eval
from pioreactor.utils.splines import spline_eval_derivative
from pioreactor.utils.splines import spline_fit
from pioreactor.utils.splines import spline_fit_interpolating
from pioreactor.utils.splines import spline_solve
from scipy.interpolate import CubicSpline


def _spline_data(knots: list[float], coefficients: list[list[float]]) -> structs.SplineFitData:
    return structs.SplineFitData(knots=knots, coefficients=coefficients)


def test_public_fit_docstrings_are_visible() -> None:
    assert spline_fit.__doc__ is not None
    assert "Fit a natural cubic regression spline." in spline_fit.__doc__
    assert spline_fit_interpolating.__doc__ is not None
    assert (
        "Fit a natural cubic spline that interpolates every data point." in spline_fit_interpolating.__doc__
    )


def test_spline_fit_and_eval_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    spline_data = spline_fit(x, y, knots=2)

    assert spline_eval(spline_data, 2.5) == pytest.approx(6.0, rel=1e-6)
    assert spline_eval(spline_data, -1.0) == pytest.approx(-1.0, rel=1e-6)


def test_spline_fit_auto_selects_knots() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    spline_data = spline_fit(x, y, knots="auto")

    assert spline_eval(spline_data, 2.5) == pytest.approx(6.0, rel=1e-6)
    assert spline_data.knots[0] == pytest.approx(min(x), rel=1e-6)
    assert spline_data.knots[-1] == pytest.approx(max(x), rel=1e-6)


def test_spline_fit_auto_selects_knots_with_two_observations() -> None:
    x = [0.0, 2.0]
    y = [1.0, 5.0]
    spline_data = spline_fit(x, y, knots="auto")

    expected = np.interp([0.5, 1.5], x, y)
    assert spline_data.knots == pytest.approx([0.0, 2.0], rel=1e-6)
    assert spline_eval(spline_data, 0.5) == pytest.approx(expected[0], rel=1e-6)
    assert spline_eval(spline_data, 1.5) == pytest.approx(expected[1], rel=1e-6)


def test_spline_fit_explicit_knots_interpolate_at_knots() -> None:
    x = [0.0, 1.0, 2.0]
    y = [0.0, 1.0, 0.0]
    spline_data = spline_fit(x, y, knots=[0.0, 1.0, 2.0])

    for x_value, y_value in zip(x, y):
        assert spline_eval(spline_data, x_value) == pytest.approx(y_value, rel=1e-6)


def test_spline_solve_linear_with_extrapolation() -> None:
    x = [0.0, 1.0]
    y = [1.0, 3.0]
    spline_data = spline_fit(x, y, knots=2)

    solutions = spline_solve(spline_data, 7.0)
    assert solutions == pytest.approx([3.0], rel=1e-6)

    solutions = spline_solve(spline_data, 1.0)
    assert solutions == pytest.approx([0.0], rel=1e-6)


def test_spline_solve_multiple_solutions() -> None:
    spline_data = _spline_data(
        [0.0, 1.0, 2.0],
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, -1.0, 0.0, 0.0],
        ],
    )

    solutions = spline_solve(spline_data, 0.5)
    assert solutions == pytest.approx([0.5, 1.5], rel=1e-6)


def test_spline_fit_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        spline_fit([0.0, 1.0], [0.0], knots=2)

    with pytest.raises(ValueError):
        spline_fit([1.0, 1.0], [0.0, 1.0], knots=2)

    with pytest.raises(ValueError):
        spline_fit([0.0, 1.0], [0.0, 1.0], knots=1)

    with pytest.raises(ValueError):
        spline_fit([0.0, 1.0], [0.0, 1.0], knots=[])

    with pytest.raises(ValueError):
        spline_fit([0.0, 1.0], [0.0, 1.0], knots=2, weights=[1.0])

    with pytest.raises(ValueError):
        spline_fit([0.0, 1.0], [0.0, 1.0], knots=2, weights=[1.0, -1.0])


def test_spline_eval_rejects_bad_spline_data() -> None:
    with pytest.raises(ValueError):
        spline_eval(cast(structs.SplineFitData, [0.0, 1.0]), 1.0)

    with pytest.raises(ValueError):
        spline_eval(_spline_data([0.0, 1.0], [[0.0, 1.0, 0.0]]), 1.0)

    with pytest.raises(ValueError):
        spline_eval(_spline_data([1.0, 0.0], [[0.0, 1.0, 0.0, 0.0]]), 1.0)


def test_spline_solve_rejects_bad_spline_data() -> None:
    with pytest.raises(ValueError):
        spline_solve(_spline_data([0.0, 1.0], [[0.0, 1.0, 0.0]]), 1.0)

    with pytest.raises(ValueError):
        spline_solve(_spline_data([0.0, 1.0, 1.0], [[0.0, 1.0, 0.0, 0.0]]), 1.0)


def test_spline_fit_matches_known_knot_values() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [2.0, 1.0, 3.0, 0.0]
    spline_data = spline_fit(x, y, knots=[0.0, 1.0, 2.0, 3.0])

    for x_value, y_value in zip(x, y):
        assert spline_eval(spline_data, x_value) == pytest.approx(y_value, rel=1e-6)


def test_spline_eval_matches_numpy_interpolation_for_two_knots() -> None:
    x = [0.0, 2.0]
    y = [1.0, 5.0]
    spline_data = spline_fit(x, y, knots=2)

    expected = np.interp([0.5, 1.5], x, y)
    assert spline_eval(spline_data, 0.5) == pytest.approx(expected[0], rel=1e-6)
    assert spline_eval(spline_data, 1.5) == pytest.approx(expected[1], rel=1e-6)


def test_spline_fit_weighted_biases_toward_heavy_points() -> None:
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [0.0, 1.0, 4.0, 3.0, 4.0]
    weights = [1.0, 1.0, 50.0, 1.0, 1.0]

    unweighted = spline_fit(x, y, knots=3)
    weighted = spline_fit(x, y, knots=3, weights=weights)

    target = 4.0
    weighted_error = abs(spline_eval(weighted, 2.0) - target)
    unweighted_error = abs(spline_eval(unweighted, 2.0) - target)

    assert weighted_error < unweighted_error


def test_spline_fit_reduces_residuals_on_noisy_linear_data() -> None:
    rng = np.random.default_rng(12345)
    x = np.linspace(0.0, 10.0, 25)
    y = 2.5 * x - 1.25 + rng.normal(0.0, 0.2, size=x.size)
    spline_data = spline_fit(x.tolist(), y.tolist(), knots=4)

    y_pred = np.array([spline_eval(spline_data, float(xi)) for xi in x])
    mse = np.mean((y_pred - y) ** 2)
    assert mse < 0.2


def test_spline_fit_auto_selects_linear_curve_for_noisy_linear_data() -> None:
    rng = np.random.default_rng(123)
    x = np.linspace(0.0, 10.0, 30)
    y = 2.5 * x - 1.0 + rng.normal(0.0, 0.1, size=x.size)
    spline_data = spline_fit(x.tolist(), y.tolist(), knots="auto")

    knots, coefficients = spline_data.knots, spline_data.coefficients
    assert len(knots) == 2
    assert len(coefficients) == 1
    assert coefficients[0][2] == pytest.approx(0.0, abs=1e-12)
    assert coefficients[0][3] == pytest.approx(0.0, abs=1e-12)


# OD standards from a user report: dense at low OD, sparse up to OD 4.
USER_OD600 = [0.0, 0.03, 0.17, 0.40, 0.64, 1.03, 1.59, 2.21, 4.12]
USER_VOLTAGES = [0.0, 0.0005, 0.006, 0.017, 0.035, 0.064, 0.128, 0.211, 0.360]
# A response shaped like those standards: convex at low OD, flattening by OD 4.
CURVED_OD_RESPONSE = np.polyfit(USER_OD600, USER_VOLTAGES, deg=3)
DILUTION_SERIES = [0.0, 0.0625, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0]


def _eval_on(spline_data: structs.SplineFitData, xs: np.ndarray | list[float]) -> np.ndarray:
    return np.array([spline_eval(spline_data, float(x)) for x in xs])


def test_spline_fit_auto_bends_for_od_standards_clustered_at_low_od() -> None:
    # quantile knots alone gave a near-linear fit that missed the curvature here.
    spline_data = spline_fit(USER_OD600, USER_VOLTAGES, knots="auto")

    assert len(spline_data.knots) > 2

    preds = _eval_on(spline_data, USER_OD600)
    line = np.polyval(np.polyfit(USER_OD600, USER_VOLTAGES, deg=1), USER_OD600)
    assert np.sum((preds - USER_VOLTAGES) ** 2) < 0.1 * np.sum((line - USER_VOLTAGES) ** 2)

    grid = np.linspace(0.0, max(USER_OD600), 200)
    assert np.all(np.diff(_eval_on(spline_data, grid)) > 0)


@pytest.mark.parametrize("cluster", ["low", "high"])
def test_spline_fit_auto_tracks_curve_for_noisy_clustered_x(cluster: str) -> None:
    x = np.array(DILUTION_SERIES) if cluster == "low" else 4.0 - np.array(DILUTION_SERIES[::-1])
    grid = np.linspace(0.0, 4.0, 200)
    truth = np.polyval(CURVED_OD_RESPONSE, grid)

    for seed in range(20):
        y = np.polyval(CURVED_OD_RESPONSE, x) + np.random.default_rng(seed).normal(0.0, 0.002, x.size)
        error = _eval_on(spline_fit(x.tolist(), y.tolist(), knots="auto"), grid) - truth
        # a straight line misses this curve by ~0.02 RMSE, and a knot left in a gap in x swings by >0.1.
        assert np.sqrt(np.mean(error**2)) < 0.017, seed
        assert np.max(np.abs(error)) < 0.05, seed


def test_spline_fit_auto_stays_linear_for_noisy_linear_data_with_clustered_x() -> None:
    x = np.array(DILUTION_SERIES)
    y = 0.09 * x + np.random.default_rng(0).normal(0.0, 0.002, x.size)
    spline_data = spline_fit(x.tolist(), y.tolist(), knots="auto")

    assert len(spline_data.knots) == 2


def test_spline_fit_auto_does_not_swing_across_a_gap_in_x() -> None:
    x = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 3.8, 4.0])
    grid = np.linspace(0.0, 4.0, 200)

    for seed in range(20):
        y = np.polyval(CURVED_OD_RESPONSE, x) + np.random.default_rng(seed).normal(0.0, 0.002, x.size)
        preds = _eval_on(spline_fit(x.tolist(), y.tolist(), knots="auto"), grid)
        assert y.min() - 0.05 <= preds.min() and preds.max() <= y.max() + 0.05, seed


def test_spline_fit_auto_handles_replicate_x() -> None:
    x = np.repeat([0.0, 0.5, 1.0, 2.0, 4.0], 3)
    y = np.polyval(CURVED_OD_RESPONSE, x) + np.random.default_rng(1).normal(0.0, 0.002, x.size)
    spline_data = spline_fit(x.tolist(), y.tolist(), knots="auto")

    assert np.all(np.diff(spline_data.knots) > 0)
    grid = np.linspace(0.0, 4.0, 200)
    assert np.max(np.abs(_eval_on(spline_data, grid) - np.polyval(CURVED_OD_RESPONSE, grid))) < 0.03


def test_spline_fit_respects_sorted_or_unsorted_input() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 2.0, 0.0, 3.0]
    spline_sorted = spline_fit(x, y, knots=3)

    x_unsorted = [2.0, 0.0, 3.0, 1.0]
    y_unsorted = [0.0, 1.0, 3.0, 2.0]
    spline_unsorted = spline_fit(x_unsorted, y_unsorted, knots=3)

    for x_value in x:
        assert spline_eval(spline_sorted, x_value) == pytest.approx(
            spline_eval(spline_unsorted, x_value), rel=1e-6
        )


def test_spline_solve_cubic_interval_multiple_roots() -> None:
    # S(x) = (x - 0.2)(x - 0.6)(x - 1.4) on [0, 2]
    # Expanded: x^3 - 2.2x^2 + 1.24x - 0.168
    spline_data = _spline_data(
        [0.0, 2.0],
        [[-0.168, 1.24, -2.2, 1.0]],
    )

    solutions = spline_solve(spline_data, 0.0)
    assert solutions == pytest.approx([0.2, 0.6, 1.4], rel=1e-6)


def test_spline_fit_od_data_reduces_error_vs_poly() -> None:
    od = [0.0025, 0.007924, 0.01991, 0.05, 0.1256, 0.3155, 0.7924, 3.155, 12.56, 50.0]
    voltages = [0.0045, 0.0180, 0.1900, 0.0750, 0.0450, 0.0290, 0.0210, 0.0130, 0.0100, 0.0085]

    spline_data = spline_fit(od, voltages, knots=4)
    poly_data = np.polyfit(od, voltages, deg=3).tolist()

    spline_preds = [spline_eval(spline_data, x_val) for x_val in od]
    poly_preds = np.polyval(poly_data, od)

    spline_mse = np.mean((np.array(spline_preds) - np.array(voltages)) ** 2)
    poly_mse = np.mean((poly_preds - np.array(voltages)) ** 2)

    assert spline_mse <= poly_mse


def test_spline_eval_matches_scipy_natural_cubic_spline() -> None:
    x = np.array([0.0, 0.4, 1.0, 1.8, 2.6, 3.1, 4.0])
    y = np.array([1.0, 0.8, 1.4, 1.1, 0.3, 0.6, 1.2])

    spline_data = spline_fit_interpolating(x.tolist(), y.tolist())
    scipy_spline = CubicSpline(x, y, bc_type="natural")

    x_grid = np.linspace(x.min() - 0.5, x.max() + 0.5, 300)
    ours = np.array([spline_eval(spline_data, float(xi)) for xi in x_grid])
    theirs = scipy_spline(x_grid)

    assert np.allclose(ours, theirs, rtol=1e-10, atol=1e-10)


def test_spline_eval_derivative_matches_scipy_natural_cubic_spline() -> None:
    x = np.array([0.0, 0.4, 1.0, 1.8, 2.6, 3.1, 4.0])
    y = np.array([1.0, 0.8, 1.4, 1.1, 0.3, 0.6, 1.2])

    spline_data = spline_fit_interpolating(x.tolist(), y.tolist())
    scipy_spline = CubicSpline(x, y, bc_type="natural")

    x_grid = np.linspace(x.min() - 0.5, x.max() + 0.5, 300)
    ours = np.array([spline_eval_derivative(spline_data, float(xi)) for xi in x_grid])
    theirs = scipy_spline(x_grid, 1)

    assert np.allclose(ours, theirs, rtol=1e-10, atol=1e-10)
