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


@pytest.mark.parametrize("bad_alpha", [-0.1, 1.1, 2.0, float("nan")])
def test_alpha_out_of_range(bad_alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
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


@pytest.mark.parametrize("dt", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_pid_rejects_invalid_dt_without_changing_state(dt: float) -> None:
    client = Mock()
    pid = PID(Kp=1.0, Ki=1.0, Kd=1.0, setpoint=10.0, pub_client=client)
    pid.update(8.0, dt=1.0)
    state = (pid.error_prev, pid.error_sum, pid.derivative_prev, pid._last_input, pid._last_output)
    published = client.publish.call_count

    with pytest.raises(ValueError, match="dt must be finite and positive"):
        pid.update(9.0, dt=dt)

    assert (pid.error_prev, pid.error_sum, pid.derivative_prev, pid._last_input, pid._last_output) == state
    assert client.publish.call_count == published
