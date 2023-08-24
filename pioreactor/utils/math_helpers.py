# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Iterable

from pioreactor.utils import argextrema


def trimmed_variance(x: list) -> float:
    from statistics import variance

    x = list(x)  # copy it
    max_, min_ = max(x), min(x)
    x.remove(max_)
    x.remove(min_)
    return variance(x)


def trimmed_mean(x: list) -> float:
    from statistics import mean

    x = list(x)  # copy it
    max_, min_ = max(x), min(x)
    x.remove(max_)  # even if there is a tie, this only removes the first max_ encountered.
    x.remove(min_)
    return mean(x)


def simple_linear_regression(
    x: Iterable, y: Iterable
) -> tuple[tuple[float, float], tuple[float, float]]:
    import numpy as np

    x_ = np.array(x)
    y_ = np.array(y)

    n = x_.shape[0]
    assert n > 2, "not enough data points for linear regression"

    sum_x = np.sum(x_)
    sum_xx = np.sum(x_ * x_)
    sum_xy = np.sum(x_ * y_)
    sum_y = np.sum(y_)

    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x**2)
    bias = y_.mean() - slope * x_.mean()

    residuals_sq = ((y_ - (slope * x_ + bias)) ** 2).sum()
    std_error_slope = np.sqrt(residuals_sq / (n - 2) / (np.sum((x_ - x_.mean()) ** 2)))

    std_error_bias = np.sqrt(residuals_sq / (n - 2) / n * sum_xx / (np.sum((x_ - x_.mean()) ** 2)))

    return (float(slope), float(std_error_slope)), (float(bias), float(std_error_bias))


def simple_linear_regression_with_forced_nil_intercept(
    x: Iterable, y: Iterable
) -> tuple[tuple[float, float], tuple[float, float]]:
    import numpy as np

    x_ = np.array(x)
    y_ = np.array(y)

    n = x_.shape[0]
    assert n > 2, "not enough data points for linear regression"

    sum_xy = np.sum(x_ * y_)
    sum_xx = np.sum(x_ * x_)

    slope = sum_xy / sum_xx

    residuals_sq = np.sum((y_ - slope * x_) ** 2)
    std_error_slope = np.sqrt(residuals_sq / (n - 1) / sum_xx)

    return (float(slope), float(std_error_slope)), (0, 0.0)


def residuals_of_simple_linear_regression(x: list, y: list, trimmed=False):
    import numpy as np

    if trimmed:
        argmin_y_, argmax_y_ = argextrema(y)
        x = [v for (i, v) in enumerate(x) if (i != argmin_y_) and (i != argmax_y_)]
        y = [v for (i, v) in enumerate(y) if (i != argmin_y_) and (i != argmax_y_)]

    x_ = np.array(x)
    y_ = np.array(y)

    (slope, _), (bias, _) = simple_linear_regression(x_, y_)
    return y_ - (slope * x_ + bias)


def correlation(x: Iterable, y: Iterable) -> float:
    from statistics import stdev, mean

    mean_x, std_x = mean(x), stdev(x)
    mean_y, std_y = mean(y), stdev(y)

    if (std_y == 0) or (std_x == 0):
        return 0

    running_sum = 0
    running_count = 0
    for x_, y_ in zip(x, y):
        running_sum += (x_ - mean_x) * (y_ - mean_y)
        running_count += 1

    if running_count < 1:
        return 0

    return (running_sum / (running_count - 1)) / std_y / std_x
