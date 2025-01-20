# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Callable
from typing import TypeVar

import click

from pioreactor import structs


def green(string: str) -> str:
    return click.style(string, fg="green")


def red(string: str) -> str:
    return click.style(string, fg="red")


def bold(string: str) -> str:
    return click.style(string, bold=True)


def calculate_poly_curve_of_best_fit(x: list[float], y: list[float], degree: int) -> list[float]:
    import numpy as np

    # weigh the smallest point, the "blank measurement", more.
    # 1. It's far away from the other points
    # 2. We have prior knowledge that OD~0 when V~0.
    n = len(x)
    weights = np.ones_like(x)
    weights[0] = n / 2

    x, y = zip(*sorted(zip(x, y), key=lambda t: t[0]))  # type: ignore

    try:
        coefs = np.polyfit(x, y, deg=degree, w=weights)
    except Exception:
        click.echo("Unable to fit.")
        coefs = np.zeros(degree)

    return coefs.tolist()


def curve_to_functional_form(curve_type: str, curve_data) -> str:
    if curve_type == "poly":
        d = len(curve_data)
        return " + ".join(
            [(f"{c:0.3f}x^{d - i - 1}" if (i < d - 1) else f"{c:0.3f}") for i, c in enumerate(curve_data)]
        )
    else:
        raise NotImplementedError()


def curve_to_callable(curve_type: str, curve_data: list[float]) -> Callable:
    if curve_type == "poly":
        import numpy as np

        def curve_callable(x):
            return np.polyval(curve_data, x)

        return curve_callable

    else:
        raise NotImplementedError()


def linspace(start: float, stop: float, num: int = 50) -> list[float]:
    def linspace_(start: float, stop: float, num: int = 50):
        num = int(num)
        start = start * 1.0
        stop = stop * 1.0

        step = (stop - start) / (num - 1)

        for i in range(num):
            yield start + step * i

    return list(linspace_(start, stop, num))


def plot_data(
    x: list[float],
    y: list[float],
    title: str,
    x_label: str,
    y_label: str,
    x_min=None,
    x_max=None,
    interpolation_curve=None,
    highlight_recent_point=False,
):
    import plotext as plt  # type: ignore

    plt.clf()

    if interpolation_curve:
        x_min, x_max = min(x) - 0.1, max(x) + 0.1
        xs = linspace(x_min, x_max, num=100)
        ys = [interpolation_curve(x_) for x_ in xs]
        plt.plot(xs, ys, color=204)
        plt.plot_size(145, 26)

    plt.scatter(x, y, marker="hd")

    if highlight_recent_point:
        plt.scatter([x[-1]], [y[-1]], color=204, marker="hd")

    plt.theme("pro")
    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)

    plt.plot_size(105, 22)

    plt.xlim(x_min, x_max)
    plt.yfrequency(6)
    plt.xfrequency(6)

    plt.show()


Calb = TypeVar("Calb", bound=structs.CalibrationBase)


def crunch_data_and_confirm_with_user(calibration: Calb) -> Calb:
    y, x = calibration.recorded_data["y"], calibration.recorded_data["x"]
    candidate_curve = calibration.curve_data_

    while True:
        click.clear()

        if (candidate_curve is None) or len(candidate_curve) == 0:
            degree = 1

            if calibration.curve_type == "poly":
                candidate_curve = calculate_poly_curve_of_best_fit(x, y, degree)
            else:
                raise ValueError("only poly supported")

        curve_callable = curve_to_callable("poly", candidate_curve)
        plot_data(
            x,
            y,
            interpolation_curve=curve_callable,
            highlight_recent_point=False,
            title="Calibration Curve",
            x_label=calibration.x,
            y_label=calibration.y,
        )
        click.echo()

        click.echo(f"Calibration curve: {curve_to_functional_form(calibration.curve_type, candidate_curve)}")
        r = click.prompt(
            green(
                f"""
y: confirm and save to disk
q: exit completely
d: choose a new degree for polynomial fit (currently {len(candidate_curve)-1})
"""
            ),
            type=click.Choice(["y", "q", "d"]),
        )
        if r == "y":
            calibration.curve_data_ = candidate_curve
            return calibration
        elif r == "n":
            return calibration
        elif r == "d":
            degree = click.prompt(green("Enter new degree"), type=click.IntRange(1, 5, clamp=True))

            if calibration.curve_type == "poly":
                candidate_curve = calculate_poly_curve_of_best_fit(x, y, degree)
            else:
                raise ValueError("only poly supported")

        else:
            return calibration
