# -*- coding: utf-8 -*-
# test_streaming_calculations.py
from math import isfinite
from unittest.mock import Mock

import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.utils.streaming_calculations import PID


@settings(max_examples=100)
@given(
    alpha=st.floats(0, 1, allow_nan=False, allow_infinity=False),
    values=st.lists(st.floats(-100, 100, allow_nan=False, allow_infinity=False), min_size=1, max_size=30),
)
def test_property_ema_stays_within_observed_range(alpha: float, values: list[float]) -> None:
    ema = ExponentialMovingAverage(alpha)
    lower = upper = values[0]
    for value in values:
        lower, upper = min(lower, value), max(upper, value)
        result = ema.update(value)
        assert isfinite(result)
        # Convex combinations can round just outside the observed range.
        assert lower - 1e-10 <= result <= upper + 1e-10
        assert ema.get_latest() == result


@settings(max_examples=100)
@given(
    alpha=st.sampled_from([0.0, 1.0]),
    values=st.lists(st.floats(-100, 100, allow_nan=False, allow_infinity=False), min_size=1, max_size=30),
)
def test_property_ema_endpoints_select_latest_or_first(alpha: float, values: list[float]) -> None:
    ema = ExponentialMovingAverage(alpha)
    for value in values:
        assert ema.update(value) == (value if alpha == 0.0 else values[0])


@settings(max_examples=100)
@given(
    gains=st.tuples(*(st.floats(-10, 10, allow_nan=False, allow_infinity=False) for _ in range(3))),
    setpoint=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    lower=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    width=st.floats(0, 100, allow_nan=False, allow_infinity=False),
    smoothing=st.floats(0, 1, allow_nan=False, allow_infinity=False),
    updates=st.lists(
        st.tuples(
            st.floats(-100, 100, allow_nan=False, allow_infinity=False),
            st.floats(0.01, 10, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=30,
    ),
)
def test_property_pid_respects_output_limits(
    gains: tuple[float, float, float],
    setpoint: float,
    lower: float,
    width: float,
    smoothing: float,
    updates: list[tuple[float, float]],
) -> None:
    upper = lower + width
    pid = PID(
        Kp=gains[0],
        Ki=gains[1],
        Kd=gains[2],
        setpoint=setpoint,
        output_limits=(lower, upper),
        derivative_smoothing=smoothing,
        pub_client=Mock(),
    )
    for value, dt in updates:
        output = pid.update(value, dt=dt)
        assert isfinite(output)
        assert lower <= output <= upper


@settings(max_examples=100)
@given(
    updates=st.lists(
        st.tuples(
            st.floats(-100, 100, allow_nan=False, allow_infinity=False),
            st.floats(0.01, 10, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=30,
    ),
    bad_dt=st.one_of(
        st.sampled_from([0.0, float("nan"), float("inf"), -float("inf")]),
        st.floats(-1000, 0, allow_nan=False, allow_infinity=False),
    ),
    value=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
)
def test_property_pid_invalid_dt_preserves_state_and_publications(
    updates: list[tuple[float, float]], bad_dt: float, value: float
) -> None:
    client = Mock()
    pid = PID(Kp=1.0, Ki=1.0, Kd=1.0, setpoint=10.0, pub_client=client)
    for input_, dt in updates:
        pid.update(input_, dt=dt)
    state = (pid.error_prev, pid.error_sum, pid.derivative_prev, pid._last_input, pid._last_output)
    publications = client.publish.call_args_list.copy()

    with pytest.raises(ValueError, match="dt must be finite and positive"):
        pid.update(value, dt=bad_dt)

    assert (pid.error_prev, pid.error_sum, pid.derivative_prev, pid._last_input, pid._last_output) == state
    assert client.publish.call_args_list == publications


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


def test_pid_anti_windup_bounds_the_integral_term_not_the_error_sum() -> None:
    # A negative-gain controller, as in pid_morbidostat: input above the setpoint should raise the output.
    pid = PID(0.0, -0.5, 0.0, setpoint=0.2, output_limits=(0, 1), pub_client=Mock())

    for _ in range(3):
        output = pid.update(0.5, dt=1.0)  # error = -0.3

    assert pid.error_sum == pytest.approx(-0.9)
    assert output == pytest.approx(0.45)

    for _ in range(20):
        output = pid.update(0.5, dt=1.0)

    assert output == pytest.approx(1.0)
    assert pid.Ki * pid.error_sum == pytest.approx(1.0)
