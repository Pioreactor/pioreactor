# -*- coding: utf-8 -*-
import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from pioreactor.background_jobs.base import compute_od_timing
from pioreactor.exc import DodgingTimingError


@settings(max_examples=100)
@given(
    costs=st.tuples(*(st.integers(0, 800) for _ in range(4))),
    slack=st.integers(1, 800),
    elapsed=st.integers(0, 100_000),
    shift=st.integers(-1_000_000, 1_000_000),
)
def test_property_od_timing_respects_budget_and_clock_translation(
    costs: tuple[int, int, int, int], slack: int, elapsed: int, shift: int
) -> None:
    # Eighth-second ticks are exactly representable, including at Unix timestamp scale.
    interval = (sum(costs) + slack) / 8
    od_duration, pre_delay, post_delay, after_action = (cost / 8 for cost in costs)
    origin = 1_700_000_000.0
    kwargs = dict(
        interval=interval,
        od_duration=od_duration,
        pre_delay=pre_delay,
        post_delay=post_delay,
        after_action=after_action,
    )
    timing = compute_od_timing(first_od_obs_time=origin, now=origin + elapsed / 8, **kwargs)
    translated = compute_od_timing(
        first_od_obs_time=origin + shift, now=origin + elapsed / 8 + shift, **kwargs
    )

    assert 0 < timing["time_to_next_od"] <= interval
    assert 0 <= timing["wait_window"] <= slack / 8
    assert timing["wait_window"] <= max(0.0, timing["time_to_next_od"] - pre_delay)
    assert translated == timing


@settings(max_examples=100)
@given(
    costs=st.tuples(*(st.integers(1, 800) for _ in range(4))),
    deficit=st.integers(0, 3),
    elapsed=st.integers(0, 100_000),
)
def test_property_od_timing_rejects_exhausted_budget(
    costs: tuple[int, int, int, int], deficit: int, elapsed: int
) -> None:
    od_duration, pre_delay, post_delay, after_action = (cost / 8 for cost in costs)
    with pytest.raises(DodgingTimingError):
        compute_od_timing(
            interval=(sum(costs) - deficit) / 8,
            first_od_obs_time=1_700_000_000.0,
            now=1_700_000_000.0 + elapsed / 8,
            od_duration=od_duration,
            pre_delay=pre_delay,
            post_delay=post_delay,
            after_action=after_action,
        )


def test_compute_od_timing_happy_path() -> None:
    timing = compute_od_timing(
        interval=5.0,
        first_od_obs_time=100.0,
        now=112.0,
        od_duration=1.0,
        pre_delay=1.5,
        post_delay=0.5,
        after_action=0.2,
    )

    # now - first = 12, 12 % 5 = 2, so time_to_next_od = 3
    assert timing["time_to_next_od"] == pytest.approx(3.0)
    assert timing["wait_window"] == pytest.approx(1.5)


def test_compute_od_timing_wait_window_tracks_actual_next_od_when_timer_is_late() -> None:
    timing = compute_od_timing(
        interval=10.0,
        first_od_obs_time=100.0,
        now=107.5,
        od_duration=1.0,
        pre_delay=1.0,
        post_delay=0.5,
        after_action=0.1,
    )

    assert timing["time_to_next_od"] == pytest.approx(2.5)
    assert timing["wait_window"] == pytest.approx(1.5)


def test_compute_od_timing_wraps_to_full_interval_when_on_boundary() -> None:
    """
    When `now` sits exactly on an interval boundary, the next OD should be treated as one full
    interval away (not immediately), so time_to_next_od should equal the interval, not 0.
    """
    timing = compute_od_timing(
        interval=5.0,
        first_od_obs_time=100.0,
        now=105.0,
        od_duration=1.0,
        pre_delay=1.5,
        post_delay=0.5,
        after_action=0.2,
    )

    assert timing["time_to_next_od"] == pytest.approx(5.0)


def test_compute_od_timing_raises_when_budget_is_negative() -> None:
    with pytest.raises(DodgingTimingError):
        compute_od_timing(
            interval=4.0,
            first_od_obs_time=0.0,
            now=1.0,
            od_duration=1.0,
            pre_delay=1.5,
            post_delay=1.5,
            after_action=0.6,
        )
