# -*- coding: utf-8 -*-
# test_streaming_calculations.py
from unittest.mock import Mock

import pytest
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.utils.streaming_calculations import PID


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


@pytest.mark.parametrize("derivative_smoothing", [0.0, 0.5])
def test_pid_reset_clears_derivative_history(derivative_smoothing: float) -> None:
    pid = PID(
        Kp=0.0,
        Ki=0.0,
        Kd=1.0,
        setpoint=0.0,
        derivative_smoothing=derivative_smoothing,
        pub_client=Mock(),
    )
    pid.update(10.0)
    pid.update(15.0)

    pid.reset()

    assert pid.update(20.0) == 0.0
    assert pid.update(25.0) == pytest.approx(-5.0 * (1 - derivative_smoothing))
