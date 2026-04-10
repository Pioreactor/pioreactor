# -*- coding: utf-8 -*-
# test_streaming_calculations.py
import pytest
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage


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
