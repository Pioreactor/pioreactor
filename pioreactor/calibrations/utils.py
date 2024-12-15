from typing import Callable



def curve_to_callable(curve_type: str, curve_data: list[float]) -> Callable:
    if curve_type == "poly":
        import numpy as np

        def curve_callable(x):
            return np.polyval(curve_data, x)

        return curve_callable

    else:
        raise NotImplementedError


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
