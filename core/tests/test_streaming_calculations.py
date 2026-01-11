# -*- coding: utf-8 -*-
# test_streaming_calculations.py
import pytest
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.utils.streaming_calculations import ExponentialMovingStd


def test_ema_get_latest_and_clear() -> None:
    ema = ExponentialMovingAverage(alpha=0.3)
    with pytest.raises(ValueError):
        ema.get_latest()

    ema.update(5.0)
    assert ema.get_latest() == pytest.approx(5.0)

    ema.clear()
    with pytest.raises(ValueError):
        ema.get_latest()


@pytest.mark.parametrize("bad_alpha", [-0.1, 1.1, 2.0])
def test_alpha_out_of_range(bad_alpha) -> None:
    with pytest.raises(ValueError):
        ExponentialMovingAverage(bad_alpha)

    with pytest.raises(ValueError):
        ExponentialMovingStd(bad_alpha)


# -----------------  ExponentialMovingStd  ----------------- #


def test_std_first_point_returns_none() -> None:
    std = ExponentialMovingStd(alpha=0.5)
    assert std.update(10) is None  # first sample: no std yet


def test_std_constant_stream_zero_variance() -> None:
    std = ExponentialMovingStd(alpha=0.2)
    for _ in range(5):
        out = std.update(42.0)
    assert out == pytest.approx(0.0, abs=1e-15)


@pytest.mark.parametrize(
    "mu, sigma",
    [
        (0.0, 1.0),
        (5.0, 2.0),
        (-3.0, 0.5),
        (10.0, 3.0),
    ],
)
def test_known_distribution(mu, sigma) -> None:
    import random

    std = ExponentialMovingStd(alpha=0.999)
    for i in range(10_000):
        std.update(random.gauss(mu=mu, sigma=sigma))

    assert std.ema.value == pytest.approx(mu, abs=0.2)  # allow some tolerance due to randomness
    assert std.value == pytest.approx(sigma, abs=0.2)  # allow some tolerance due to randomness


def test_std_with_initial_values() -> None:
    std0 = 3.0
    std = ExponentialMovingStd(alpha=0.3, initial_std_value=std0, initial_mean_value=10.0)
    assert std.get_latest() == pytest.approx(std0)

    # next update should move a little, but not blow up
    new = std.update(10.0)
    assert isinstance(new, float)
    assert new >= 0.0
    assert abs(new - std0) < 5.0  # arbitrary sanity bound
