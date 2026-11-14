# -*- coding: utf-8 -*-
"""Conservative Hall interval hypotheses; only extra-edge merges are used for feedback."""
from math import isfinite
from statistics import median
from typing import NamedTuple
from typing import Sequence


class IntervalCorrection(NamedTuple):
    count_adjustment: int
    reason: str
    interval_index: int


def suggest_interval_correction(intervals: Sequence[float]) -> IntervalCorrection | None:
    """Suggest at most one extra/missing edge in an otherwise steady window.

    Require at least five unaffected intervals within 10% of the window median.
    A split must contain two intervals each below 85% of that median, whose sum
    is within 10%; a doubled interval must be within 10% of two periods. Reject
    ambiguous/multiple defects, nonpositive intervals and gaps longer than two
    periods. These thresholds are diagnostic heuristics, not proof of bad edges.
    Callers must supply the complete window, never a truncated prefix.
    """
    if len(intervals) < 6 or any(not isfinite(dt) or dt <= 0 for dt in intervals):
        return None
    period = median(intervals)
    normal = [abs(dt / period - 1.0) <= 0.10 for dt in intervals]
    abnormal_count = normal.count(False)
    candidates = []
    for i, dt in enumerate(intervals):
        if abnormal_count == 1 and not normal[i] and abs(dt / (2 * period) - 1.0) <= 0.10:
            candidates.append(IntervalCorrection(1, "possible_missing_edge", i))
        if (
            len(intervals) >= 7
            and abnormal_count == 2
            and i + 1 < len(intervals)
            and dt < 0.85 * period
            and intervals[i + 1] < 0.85 * period
            and abs((dt + intervals[i + 1]) / period - 1.0) <= 0.10
        ):
            candidates.append(IntervalCorrection(-1, "possible_extra_edge", i))
    return candidates[0] if len(candidates) == 1 else None
