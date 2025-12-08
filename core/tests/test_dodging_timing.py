# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.background_jobs.base import compute_od_timing
from pioreactor.exc import DodgingTimingError


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

    assert timing["wait_window"] == pytest.approx(1.8)
    # now - first = 12, 12 % 5 = 2, so time_to_next_od = 3
    assert timing["time_to_next_od"] == pytest.approx(3.0)


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
