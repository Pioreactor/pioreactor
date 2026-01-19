# -*- coding: utf-8 -*-
import numpy as np
import pytest
from pioreactor.utils.splines import spline_eval
from pioreactor.utils.splines import spline_fit
from pioreactor.utils.splines import spline_solve


def test_spline_fit_and_eval_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    spline_data = spline_fit(x, y, knots=2)

    assert spline_eval(spline_data, 2.5) == pytest.approx(6.0, rel=1e-6)
    assert spline_eval(spline_data, -1.0) == pytest.approx(-1.0, rel=1e-6)


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
    spline_data = [
        [0.0, 1.0, 2.0],
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, -1.0, 0.0, 0.0],
        ],
    ]

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
        spline_eval([0.0, 1.0], 1.0)

    with pytest.raises(ValueError):
        spline_eval([[0.0, 1.0], [[0.0, 1.0, 0.0]]], 1.0)

    with pytest.raises(ValueError):
        spline_eval([[1.0, 0.0], [[0.0, 1.0, 0.0, 0.0]]], 1.0)


def test_spline_solve_rejects_bad_spline_data() -> None:
    with pytest.raises(ValueError):
        spline_solve([[0.0, 1.0], [[0.0, 1.0, 0.0]]], 1.0)

    with pytest.raises(ValueError):
        spline_solve([[0.0, 1.0, 1.0], [[0.0, 1.0, 0.0, 0.0]]], 1.0)


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
    spline_data = [
        [0.0, 2.0],
        [[-0.168, 1.24, -2.2, 1.0]],
    ]

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
