# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Callable
import click



def green(string: str) -> str:
    return click.style(string, fg="green")

def red(string: str) -> str:
    return click.style(string, fg="red")


def bold(string: str) -> str:
    return click.style(string, bold=True)


def calculate_curve_of_best_fit(
    x: list[float], y: list[float], degree: int
) -> tuple[list[float], str]:
    import numpy as np

    # weigh the last point, the "blank measurement", more.
    # 1. It's far away from the other points
    # 2. We have prior knowledge that OD~0 when V~0.
    n = len(voltages)
    weights = np.ones_like(voltages)
    weights[-1] = n / 2

    try:
        coefs = np.polyfit(inferred_od600s, voltages, deg=degree, w=weights).tolist()
    except Exception:
        echo("Unable to fit.")
        coefs = np.zeros(degree).tolist()

    return coefs, "poly"

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
        plt.plot(sorted(x), [interpolation_curve(x_) for x_ in sorted(x)], color=204)
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



def crunch_data_and_confirm_with_user(
    calibration
) -> bool:

    click.clear()

    y, x = calibration.recorded_data["y"], calibration.recorded_data["x"]
    candidate_curve = calibration.curve_data_

    while True:

        if candidate_curve is not None:
            degree = 1
            candidate_curve = calculate_curve_of_best_fit(x, y, degree)


        curve_callable = curve_to_callable("poly", candidate_curve)
        plot_data(
            x,
            y,
            interpolation_curve=curve_callable,
            highlight_recent_point=False,
        )
        click.echo()
        click.echo(f"Calibration curve: {curve_to_functional_form(curve_type, candidate_curve)}")
        r = click.prompt(
            green(
                f"""
    y: confirm and save to disk
    n: exit completely
    d: choose a new degree for polynomial fit (currently {len(candidate_curve)-1})

    """
            ),
            type=click.Choice(["y", "n", "d"]),
        )
        if r == "y":
            calibration.curve_data_ = candidate_curve
            return True
        elif r == "n":
            return False
        elif r == "d":
            degree = click.prompt(green("Enter new degree"), type=click.IntRange(1, 5, clamp=True))
        else:
            return False
