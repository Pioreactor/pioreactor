# -*- coding: utf-8 -*-
from typing import Callable
from typing import TypeVar

import click
from pioreactor import structs
from pioreactor.calibrations.cli_helpers import green
from pioreactor.calibrations.cli_helpers import info
from pioreactor.calibrations.cli_helpers import red
from pioreactor.utils.polys import poly_eval
from pioreactor.utils.polys import poly_fit


def calculate_poly_curve_of_best_fit(
    x: list[float], y: list[float], degree: int, weights: list[float] | None = None
) -> list[float]:
    if weights is None:
        weights = [1.0] * len(x)

    assert len(weights) == len(x) == len(y)

    # sort by y, since we want calibrations to be easily solvable from y to x (this mostly applies to OD cal with weights.)
    y, x, weights = zip(*sorted(zip(y, x, weights), key=lambda t: t[0]))  # type: ignore

    try:
        coefs = poly_fit(x, y, degree=degree, weights=weights)
    except Exception:
        click.echo(red("Unable to fit."))
        coefs = [0.0] * (degree + 1)

    return list(coefs)


def curve_to_functional_form(curve_type: str, curve_data) -> str:
    if curve_type == "poly":
        d = len(curve_data)
        return " + ".join(
            [(f"{c:0.3f}x^{d - i - 1}" if (i < d - 1) else f"{c:0.3f}") for i, c in enumerate(curve_data)]
        )
    elif curve_type == "spline":
        if not isinstance(curve_data, list) or len(curve_data) != 2:
            raise ValueError("Invalid spline data.")
        knots = curve_data[0]
        return f"natural cubic spline with {len(knots)} knots"
    else:
        raise NotImplementedError()


def curve_to_callable(curve_type: str, curve_data: list[float] | list) -> Callable[[float], float]:
    if curve_type == "poly":

        def curve_callable(x: float):
            return poly_eval(curve_data, x)

        return curve_callable

    elif curve_type == "spline":
        from pioreactor.utils.splines import spline_eval

        def curve_callable(x: float):
            return spline_eval(curve_data, x)

        return curve_callable

    else:
        raise NotImplementedError()


def linspace(start: float, stop: float, num: int = 50, *, precision: int = 3) -> list[float]:
    """
    Return ``num`` evenly-spaced values from *start* to *stop*, rounded to *precision*
    decimal places (default = 3).
    """
    if num <= 0:
        raise ValueError("num must be > 0")
    if num == 1:  # avoid division-by-zero
        return [round(start, precision)]

    step = (stop - start) / (num - 1)
    return [round(start + step * i, precision) for i in range(num)]


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


def crunch_data_and_confirm_with_user(
    calibration: Calb,
    initial_degree: int = 1,
    weights: list[float] | None = None,
    *,
    fit: str = "poly",
    initial_knots: int = 4,
) -> Calb:
    y, x = calibration.recorded_data["y"], calibration.recorded_data["x"]
    candidate_curve = calibration.curve_data_
    if calibration.curve_type != fit:
        candidate_curve = []
        calibration.curve_type = fit

    while True:
        click.clear()

        if len(candidate_curve) == 0:
            if fit == "poly":
                if len(x) - 1 < initial_degree:
                    info(
                        f"Degree is too high for {len(x)} observed data points. Clamping degree to {len(x) - 1}"
                    )
                    initial_degree = len(x) - 1

                degree = initial_degree
                candidate_curve = calculate_poly_curve_of_best_fit(x, y, degree, weights)
            elif fit == "spline":
                from pioreactor.utils.splines import spline_fit

                knots = max(2, min(initial_knots, len(x)))
                if knots != initial_knots:
                    info(f"Knots count adjusted to {knots} for {len(x)} observed data points.")
                    initial_knots = knots

                candidate_curve = spline_fit(x, y, knots=knots, weights=weights)
            else:
                raise ValueError("only `poly` or `spline` supported")

        curve_callable = curve_to_callable(fit, candidate_curve)
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

        info(f"Calibration curve: {curve_to_functional_form(fit, candidate_curve)}")
        r = click.prompt(
            green(
                f"""
y: confirm curve
q: exit
{_fit_prompt_hint(fit, candidate_curve)}
"""
            ),
            type=click.Choice(_fit_prompt_choices(fit)),
            prompt_suffix=": ",
        )
        if r == "y":
            calibration.curve_data_ = candidate_curve
            return calibration
        elif r == "d":
            if fit != "poly":
                raise ValueError("only poly supports degree selection")
            degree = click.prompt(
                green("Enter new degree"),
                type=click.IntRange(1, 5, clamp=True),
                prompt_suffix=": ",
            )
            candidate_curve = calculate_poly_curve_of_best_fit(x, y, degree, weights)
        elif r == "k":
            if fit != "spline":
                raise ValueError("only spline supports knot selection")
            from pioreactor.utils.splines import spline_fit

            knots = click.prompt(
                green("Enter new knot count"),
                type=click.IntRange(2, max(2, len(x)), clamp=True),
                prompt_suffix=": ",
            )
            candidate_curve = spline_fit(x, y, knots=knots, weights=weights)

        else:
            raise click.Abort()


def _fit_prompt_choices(fit: str) -> list[str]:
    if fit == "poly":
        return ["y", "q", "d"]
    if fit == "spline":
        return ["y", "q", "k"]
    return ["y", "q"]


def _fit_prompt_hint(fit: str, candidate_curve) -> str:
    if fit == "poly":
        return f"d: choose a new degree for polynomial fit (currently {len(candidate_curve) - 1})"
    if fit == "spline":
        knots_count = len(candidate_curve[0]) if isinstance(candidate_curve, list) else 0
        return f"k: choose a new knot count (currently {knots_count})"
    return ""
