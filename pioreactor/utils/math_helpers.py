# -*- coding: utf-8 -*-
# math_helpers.py


def simple_linear_regression(x, y):
    import numpy as np

    x = np.array(x)
    y = np.array(y)

    n = x.shape[0]
    assert n > 2, "not enough data points for linear regression"

    sum_x = np.sum(x)
    sum_xx = np.sum(x * x)

    slope = (n * np.sum(x * y) - sum_x * np.sum(y)) / (n * sum_xx - sum_x ** 2)
    bias = y.mean() - slope * x.mean()

    residuals_sq = ((y - (slope * x + bias)) ** 2).sum()
    std_error_slope = np.sqrt(residuals_sq / (n - 2) / (np.sum((x - x.mean()) ** 2)))

    std_error_bias = np.sqrt(
        residuals_sq / (n - 2) / n * sum_xx / (np.sum((x - x.mean()) ** 2))
    )

    return (slope, std_error_slope), (bias, std_error_bias)


def residuals_of_simple_linear_regression(x, y):
    import numpy as np

    x = np.array(x)
    y = np.array(y)

    (slope, _), (bias, _) = simple_linear_regression(x, y)
    return y - (slope * x + bias)


def correlation(x, y) -> float:
    from statistics import stdev, mean

    mean_x, std_x = mean(x), stdev(x)
    mean_y, std_y = mean(y), stdev(y)

    if (std_y == 0) or (std_x == 0):
        return 0

    running_sum = 0
    running_count = 0
    for (x_, y_) in zip(x, y):
        running_sum += (x_ - mean_x) * (y_ - mean_y)
        running_count += 1

    if running_count < 1:
        return 0

    return (running_sum / (running_count - 1)) / std_y / std_x
