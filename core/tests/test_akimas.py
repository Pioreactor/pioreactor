# -*- coding: utf-8 -*-
from __future__ import annotations

import numpy as np
import pytest
from pioreactor.utils.akimas import akima_eval
from pioreactor.utils.akimas import akima_fit
from pioreactor.utils.akimas import akima_solve
from scipy.interpolate import Akima1DInterpolator


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


def test_akima_solve_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    akima_data = akima_fit(x, y)

    solutions = akima_solve(akima_data, 5.0)
    assert solutions == pytest.approx([2.0], rel=1e-6)


def test_akima_allows_duplicate_x_by_averaging() -> None:
    akima_data = akima_fit([0.0, 1.0, 1.0], [0.0, 1.0, 3.0])
    assert akima_eval(akima_data, 1.0) == pytest.approx(2.0)


def test_akima_fit_requires_matching_lengths() -> None:
    with pytest.raises(ValueError, match="x and y must have the same length"):
        akima_fit([0.0, 1.0], [1.0])


def test_akima_fit_requires_two_points() -> None:
    with pytest.raises(ValueError, match="At least two data points"):
        akima_fit([0.0], [1.0])
