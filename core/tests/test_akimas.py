# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import cast

import numpy as np
import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from pioreactor import structs
from pioreactor.utils.akimas import akima_eval
from pioreactor.utils.akimas import akima_eval_derivative
from pioreactor.utils.akimas import akima_fit
from pioreactor.utils.akimas import akima_solve
from scipy.interpolate import Akima1DInterpolator


def _akima_data(knots: list[float], coefficients: list[list[float]]) -> structs.AkimaFitData:
    return structs.AkimaFitData(knots=knots, coefficients=coefficients)


def test_akima_matches_scipy() -> None:
    rng = np.random.default_rng(123)
    x = np.linspace(0.0, 10.0, 12)
    y = np.sin(x) + 0.05 * rng.normal(size=x.size)

    akima_data = akima_fit(x.tolist(), y.tolist())
    scipy_akima = Akima1DInterpolator(x, y)

    x_grid = np.linspace(x.min(), x.max(), 200)
    ours = np.array([akima_eval(akima_data, float(xi)) for xi in x_grid])
    theirs = scipy_akima(x_grid)

    assert np.allclose(ours, theirs, rtol=1e-10, atol=1e-10)


@settings(max_examples=100)
@given(
    points=st.lists(
        st.tuples(st.integers(1, 20), st.floats(-100, 100, allow_nan=False, allow_infinity=False)),
        min_size=5,
        max_size=15,
    )
)
def test_property_akima_matches_scipy(points: list[tuple[int, float]]) -> None:
    # Positive gaps generate irregular, separated knots without filtering examples.
    x = np.cumsum([gap for gap, _ in points]).astype(float)
    y = [value for _, value in points]
    curve = akima_fit(x.tolist(), y)
    reference = Akima1DInterpolator(x, y)
    probes = np.sort(np.concatenate([x, (x[:-1] + x[1:]) / 2]))

    actual = [akima_eval(curve, float(probe)) for probe in probes]
    assert actual == pytest.approx(reference(probes).tolist(), rel=1e-10, abs=1e-10)


@settings(max_examples=100)
@given(
    points=st.lists(
        st.tuples(
            st.integers(1, 20),
            st.floats(-100, 100, allow_nan=False, allow_infinity=False),
            st.floats(-100, 100, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=15,
    )
)
def test_property_akima_interpolates_duplicate_knot_means(points: list[tuple[int, float, float]]) -> None:
    knots = np.cumsum([gap for gap, _, _ in points]).astype(float).tolist()
    x = [knot for knot in knots for _ in range(2)]
    y = [value for _, first, second in points for value in (first, second)]
    # Reverse the observations to also exercise sorting before duplicate aggregation.
    curve = akima_fit(x[::-1], y[::-1])

    assert curve.knots == knots
    expected = [(first + second) / 2 for _, first, second in points]
    assert [akima_eval(curve, knot) for knot in knots] == pytest.approx(expected, rel=1e-10, abs=1e-10)


def test_akima_solve_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    akima_data = akima_fit(x, y)

    solutions = akima_solve(akima_data, 5.0)
    assert solutions == pytest.approx([2.0], rel=1e-6)


def test_akima_allows_duplicate_x_by_averaging() -> None:
    akima_data = akima_fit([0.0, 1.0, 1.0], [0.0, 1.0, 3.0])
    assert akima_eval(akima_data, 1.0) == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("x", "y"),
    [
        ([0.0, 2.0], [1.0, 5.0]),
        ([0.0, 2.0, 2.0], [1.0, 4.0, 6.0]),
    ],
)
def test_akima_two_knots_are_linear(x: list[float], y: list[float]) -> None:
    akima_data = akima_fit(x, y)

    assert akima_data.knots == [0.0, 2.0]
    assert akima_data.coefficients[0] == pytest.approx([1.0, 2.0, 0.0, 0.0])
    for point in (0.0, 0.5, 1.0, 2.0):
        assert akima_eval(akima_data, point) == pytest.approx(1.0 + 2.0 * point)
        assert akima_eval_derivative(akima_data, point) == pytest.approx(2.0)


def test_akima_fit_requires_matching_lengths() -> None:
    with pytest.raises(ValueError, match="x and y must have the same length"):
        akima_fit([0.0, 1.0], [1.0])


def test_akima_fit_requires_two_points() -> None:
    with pytest.raises(ValueError, match="At least two data points"):
        akima_fit([0.0], [1.0])


def test_akima_solve_multiple_solutions() -> None:
    akima_data = _akima_data(
        [0.0, 1.0, 2.0],
        [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, -1.0, 0.0, 0.0],
        ],
    )

    solutions = akima_solve(akima_data, 0.5)
    assert solutions == pytest.approx([0.5, 1.5], rel=1e-6)


def test_akima_eval_rejects_bad_data() -> None:
    with pytest.raises(ValueError):
        akima_eval(cast(structs.AkimaFitData, [0.0, 1.0]), 1.0)

    with pytest.raises(ValueError):
        akima_eval(_akima_data([0.0, 1.0], [[0.0, 1.0, 0.0]]), 1.0)

    with pytest.raises(ValueError):
        akima_eval(_akima_data([1.0, 0.0], [[0.0, 1.0, 0.0, 0.0]]), 1.0)


def test_akima_solve_rejects_bad_data() -> None:
    with pytest.raises(ValueError):
        akima_solve(_akima_data([0.0, 1.0], [[0.0, 1.0, 0.0]]), 1.0)

    with pytest.raises(ValueError):
        akima_solve(_akima_data([0.0, 1.0, 1.0], [[0.0, 1.0, 0.0, 0.0]]), 1.0)
