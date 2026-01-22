# -*- coding: utf-8 -*-
import numpy as np
import pytest
from pioreactor.utils.polys import poly_eval
from pioreactor.utils.polys import poly_fit
from pioreactor.utils.polys import poly_solve


def test_poly_eval_matches_numpy() -> None:
    coef = [2.0, -3.0, 1.0]
    x = 1.5
    assert poly_eval(coef, x) == pytest.approx(np.polyval(coef, x))


def test_poly_fit_matches_numpy() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 2.0, 5.0, 10.0]
    degree = 2
    assert poly_fit(x, y, degree) == pytest.approx(np.polyfit(x, y, degree).tolist())


def test_poly_fit_auto_degree_matches_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    assert poly_fit(x, y, "auto") == pytest.approx(poly_fit(x, y, 1))


def test_poly_solve_matches_numpy_roots() -> None:
    coef = [1.0, 0.0, -4.0]  # x^2 - 4
    y = 0.0
    expected = sorted([float(np.real(r)) for r in np.roots([1.0, 0.0, -4.0]) if abs(np.imag(r)) < 1e-10])
    assert poly_solve(coef, y) == pytest.approx(expected)


def test_poly_fit_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        poly_fit([], [], degree=1)

    with pytest.raises(ValueError):
        poly_fit([0.0], [1.0], degree=2)

    with pytest.raises(ValueError):
        poly_fit([0.0, 1.0], [1.0], degree=1)

    with pytest.raises(ValueError):
        poly_fit([0.0, 1.0], [1.0, 2.0], degree=-1)

    with pytest.raises(ValueError):
        poly_fit([0.0, 1.0], [1.0, 2.0], degree=1, weights=[1.0])

    with pytest.raises(ValueError):
        poly_fit([0.0, 1.0], [1.0, 2.0], degree=1, weights=[1.0, -1.0])

    with pytest.raises(ValueError):
        poly_fit([0.0, 1.0], [1.0, 2.0], degree="nope")


def test_poly_solve_rejects_empty() -> None:
    with pytest.raises(ValueError):
        poly_solve([], 1.0)
