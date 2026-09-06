# -*- coding: utf-8 -*-
import subprocess
import sys

import numpy as np
import pytest
from pioreactor import structs
from pioreactor.utils.polys import poly_eval
from pioreactor.utils.polys import poly_fit
from pioreactor.utils.polys import poly_solve


def test_poly_eval_matches_numpy() -> None:
    coef = [2.0, -3.0, 1.0]
    x = 1.5
    assert poly_eval(structs.PolyFitCoefficients(coefficients=coef), x) == pytest.approx(np.polyval(coef, x))


def test_poly_fit_matches_numpy() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 2.0, 5.0, 10.0]
    degree = 2
    assert poly_fit(x, y, degree).coefficients == pytest.approx(np.polyfit(x, y, degree).tolist())


def test_poly_fit_auto_degree_matches_linear() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    assert poly_fit(x, y, "auto") == pytest.approx(poly_fit(x, y, 1))


def test_poly_solve_matches_numpy_roots() -> None:
    coef = [1.0, 0.0, -4.0]  # x^2 - 4
    y = 0.0
    expected = sorted([float(np.real(r)) for r in np.roots([1.0, 0.0, -4.0]) if abs(np.imag(r)) < 1e-10])
    assert poly_solve(structs.PolyFitCoefficients(coefficients=coef), y) == pytest.approx(expected)


def test_poly_solve_real_root_tolerance_scales_with_root_magnitude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(np, "roots", lambda _: np.array([complex(1e9, 5e-2), complex(2.0, 5e-9)]))

    roots = poly_solve(structs.PolyFitCoefficients(coefficients=[1.0, 0.0, 1.0]), 0.0)

    assert roots == [1e9]


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
        poly_solve(structs.PolyFitCoefficients(coefficients=[]), 1.0)


@pytest.mark.parametrize("coefficients", [[0.0911, 0.0], [2.0, -3.0], [-0.5, 2.0], [0.0, 1.0]])
@pytest.mark.parametrize("value", [-10.0, 0.0, 1.0, 100.0])
def test_linear_polynomial_matches_numpy(coefficients: list[float], value: float) -> None:
    data = structs.PolyFitCoefficients(coefficients=coefficients)
    assert poly_eval(data, value) == float(np.polyval(coefficients, value))
    expected = np.roots([coefficients[0], coefficients[1] - value]).tolist()
    assert poly_solve(data, value) == expected


def test_linear_pump_conversions_do_not_import_numpy() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pioreactor.actions.pump import get_default_calibration
calibration = get_default_calibration()
calibration.curve_data_.coefficients = [0.0911, 0.0]
assert "numpy" not in sys.modules
assert calibration.duration_to_ml(calibration.ml_to_duration(1.0)) == 1.0
assert "numpy" not in sys.modules
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("coefficients, value", [([1.0, float("nan")], 1.0), ([1e-300, -1e300], 1.0)])
def test_linear_solver_preserves_numpy_errors(coefficients: list[float], value: float) -> None:
    with pytest.raises(np.linalg.LinAlgError):
        poly_solve(structs.PolyFitCoefficients(coefficients=coefficients), value)
