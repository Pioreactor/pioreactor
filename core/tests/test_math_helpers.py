# -*- coding: utf-8 -*-
# test_math_helpers
import pytest
from pioreactor.utils.math_helpers import closest_point_to_domain
from pioreactor.utils.math_helpers import simple_linear_regression
from pioreactor.utils.math_helpers import trimmed_mean


def test_simple_linear_regression_cases() -> None:
    x = [1.47, 1.50, 1.52, 1.55, 1.57, 1.60, 1.63, 1.65, 1.68, 1.70, 1.73, 1.75, 1.78, 1.80, 1.83]
    y = [
        52.21,
        53.12,
        54.48,
        55.84,
        57.20,
        58.57,
        59.93,
        61.29,
        63.11,
        64.47,
        66.28,
        68.10,
        69.92,
        72.19,
        74.46,
    ]

    (slope, std_error_slope), (intercept, std_error_intercept) = simple_linear_regression(x, y)

    assert slope == pytest.approx(61.272, rel=1e-3)
    assert intercept == pytest.approx(-39.062, rel=1e-3)
    assert std_error_slope**2 == pytest.approx(3.1539)
    assert std_error_intercept**2 == pytest.approx(8.63185)


def test_trimmed_mean() -> None:
    assert trimmed_mean([2, 2, 2, 10]) == 2.0
    assert trimmed_mean([-10, 0, 1, 10]) == 0.5
    assert trimmed_mean([-1, -10, 0, 1]) == -0.5

    assert trimmed_mean([-100, -50, 1, 2, 3, 50, 10], cut_off_n=2) == 2
    assert trimmed_mean([100, -50, -1, 0, 1, -50, 10], cut_off_n=2) == 0


def test_closest_point_single_point_in_domain() -> None:
    assert closest_point_to_domain([1.0], (0.5, 1.5)) == 1.0


def test_closest_point_multiple_points_in_domain() -> None:
    assert closest_point_to_domain([0.6, 0.8, 1.2], (0.5, 1.5)) == 0.6


def test_closest_point_all_outside_domain() -> None:
    assert closest_point_to_domain([2.0, 3.0], (0.5, 1.5)) == 2.0
    assert closest_point_to_domain([-1.0, -2.0], (0.5, 1.5)) == -1.0


def test_closest_point_empty_list() -> None:
    with pytest.raises(AssertionError):
        closest_point_to_domain([], (0.5, 1.5))


def test_closest_point_on_boundaries() -> None:
    assert closest_point_to_domain([0.5, 1.5], (0.5, 1.5)) == 0.5
