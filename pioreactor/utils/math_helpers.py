# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Sequence

from pioreactor.utils import argextrema

Number = float | int | bool


def variance(x: Sequence[Number]) -> float:
    from statistics import variance

    return variance(x)


def mean(x: Sequence[Number]) -> float:
    from statistics import mean

    return mean(x)


def trimmed_variance(x: Sequence[Number], cut_off_n=1) -> float:
    from statistics import variance

    if cut_off_n >= len(x) / 2:
        raise ValueError("cut_off_n must be less than half the length of x.")

    x = list(x)  # copy it
    x.sort()
    return variance(x[cut_off_n:-cut_off_n])


def trimmed_mean(x: Sequence[Number], cut_off_n=1) -> float:
    from statistics import mean

    x = list(x)  # copy it
    x.sort()
    return mean(x[cut_off_n:-cut_off_n])


def simple_linear_regression(
    x: Sequence[Number], y: Sequence[Number]
) -> tuple[tuple[float, float], tuple[float, float]]:
    from statistics import linear_regression

    n = len(x)
    assert n > 2, "Not enough data points for linear regression."
    assert n == len(y), "Array sizes are not equal."

    # Compute the regression using statistics.linear_regression
    slope, intercept = linear_regression(x, y)

    # Calculate residuals
    residuals = [y_i - slope * x_i - intercept for x_i, y_i in zip(x, y)]
    residuals_sq_sum = sum([r**2 for r in residuals])
    mean = sum(x) / n
    x_sq = sum([x_i**2 for x_i in x])
    x_diff_mean_sq = sum([(x_i - mean) ** 2 for x_i in x])

    # Calculate standard errors
    std_error_slope = (residuals_sq_sum / (n - 2) / x_diff_mean_sq) ** 0.5

    std_error_intercept = (residuals_sq_sum / (n - 2) * x_sq / (n * x_diff_mean_sq)) ** 0.5

    return (slope, std_error_slope), (intercept, std_error_intercept)


def simple_linear_regression_with_forced_nil_intercept(
    x: Sequence[Number], y: Sequence[Number]
) -> tuple[tuple[float, float], tuple[float, float]]:
    from statistics import linear_regression

    n = len(x)
    assert n >= 2, "not enough data points for linear regression"
    assert n == len(y), "Array sizes are not equal."

    # Compute the regression using statistics.linear_regression
    slope, intercept = linear_regression(x, y, proportional=True)
    assert intercept == 0, "Intercept should be zero for proportional=True"

    # Calculate residuals
    residuals = [y_i - slope * x_i for x_i, y_i in zip(x, y)]
    residuals_sq_sum = sum([r**2 for r in residuals])

    # Calculate standard errors
    std_error_slope = (residuals_sq_sum / (n - 1) / sum([x_i**2 for x_i in x])) ** 0.5

    return (slope, std_error_slope), (0, 0.0)


def residuals_of_simple_linear_regression(
    x: Sequence[Number], y: Sequence[Number], trimmed=False
) -> list[float]:
    if trimmed:
        argmin_y_, argmax_y_ = argextrema(y)
        x = [v for (i, v) in enumerate(x) if (i != argmin_y_) and (i != argmax_y_)]
        y = [v for (i, v) in enumerate(y) if (i != argmin_y_) and (i != argmax_y_)]

    (slope, _), (bias, _) = simple_linear_regression(x, y)
    return [y_ - (slope * x_ + bias) for (x_, y_) in zip(x, y)]


def correlation(x: Sequence[Number], y: Sequence[Number]) -> float:
    from statistics import correlation, StatisticsError

    try:
        return correlation(x, y)
    except StatisticsError as e:
        # Raising the original error with additional data
        raise StatisticsError(f"{e}. x: {x}, y: {y}") from e


def closest_point_to_domain(P: list[Number], D: tuple[Number, Number]) -> float:
    # Note: this function returns the _minimal_ found solution, if there are multiple
    a, b = D

    closest_point = None
    min_distance = float("inf")

    for p in sorted(P):
        if a <= p <= b:  # Check if p is within the domain D
            return p  # If p is within D, it's the closest point with distance 0

        distance = min(abs(p - a), abs(p - b))

        if distance < min_distance:
            min_distance = distance
            closest_point = p

    assert closest_point is not None
    return closest_point
