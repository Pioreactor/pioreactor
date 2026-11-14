# -*- coding: utf-8 -*-
"""Replay captured November 10–11 Hall intervals, rounded as in the logs."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pioreactor.background_jobs.stirring import RpmFromFrequency
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.states import JobState
from pioreactor.utils.rpm_diagnostics import suggest_interval_correction
from pioreactor.utils.timing import current_utc_datetime


# name, recorded intervals (seconds), hypothesized count adjustment, corrected RPM
TRACES = [
    (
        "pio4_live_validation",
        [0.199173, 0.199446, 0.199826, 0.201177, 0.200878, 0.200085, 0.046105, 0.153278, 0.199081, 0.198733],
        -1,
        300.4,
    ),
    (
        "pio3_live_validation",
        [0.199923, 0.200541, 0.199964, 0.199824, 0.200405, 0.200764, 0.200395, 0.057767, 0.142427, 0.200011],
        -1,
        299.7,
    ),
    (
        "pio7_split",
        [0.200272, 0.200419, 0.20043, 0.200145, 0.201287, 0.201499, 0.054261, 0.147012, 0.200788, 0.200733],
        -1,
        298.9,
    ),
    (
        "pio10_split_at_start",
        [0.056276, 0.142448, 0.199638, 0.199178, 0.19962, 0.199551, 0.198666, 0.198088, 0.200145, 0.197906],
        -1,
        301.4,
    ),
    (
        "pio3_split_at_start",
        [0.057734, 0.141202, 0.198758, 0.198873, 0.199144, 0.199119, 0.199024, 0.198838, 0.199231, 0.19921],
        -1,
        301.5,
    ),
    (
        "pio4_split",
        [0.199361, 0.199022, 0.199109, 0.199888, 0.200564, 0.199686, 0.045737, 0.151651, 0.198132, 0.198357],
        -1,
        301.4,
    ),
    (
        "pio5_missing_1800",
        [
            0.032836,
            0.034226,
            0.033495,
            0.033074,
            0.034248,
            0.033737,
            0.032755,
            0.034496,
            0.068193,
            0.03251,
            0.033513,
            0.033759,
            0.034426,
            0.03383,
            0.03323,
            0.03388,
            0.034198,
            0.033321,
            0.033976,
            0.034048,
            0.03365,
            0.03415,
            0.033679,
            0.033902,
            0.034445,
            0.033841,
            0.033445,
            0.033827,
        ],
        1,
        1777.9,
    ),
    (
        "pio5_missing_2000",
        [
            0.032514,
            0.031963,
            0.032161,
            0.032328,
            0.032243,
            0.032962,
            0.032662,
            0.031891,
            0.032209,
            0.032127,
            0.032163,
            0.0323,
            0.032302,
            0.032139,
            0.032978,
            0.033431,
            0.063206,
            0.031725,
            0.032346,
            0.032721,
            0.032514,
            0.031696,
            0.032814,
            0.033319,
            0.032549,
            0.03158,
            0.031397,
            0.032151,
            0.032228,
        ],
        1,
        1858.3,
    ),
    ("pio7_slow", [0.284496, 0.284614, 0.291659, 0.294314, 0.292391, 0.292328], 0, 206.9),
    ("pio1_half_speed_ambiguous", [0.403283, 0.39993, 0.393608, 0.396057], 0, 150.7),
    (
        "pio4_acceleration",
        [
            0.20073,
            0.188003,
            0.173297,
            0.162418,
            0.153866,
            0.147469,
            0.141623,
            0.137027,
            0.133377,
            0.130264,
            0.127553,
            0.125206,
            0.123091,
        ],
        0,
        401.3,
    ),
    (
        "pio6_settling",
        [0.172325, 0.174588, 0.179105, 0.182178, 0.184651, 0.185, 0.184407, 0.18508, 0.185081, 0.188898],
        0,
        329.4,
    ),
    (
        "pio5_high_speed",
        [
            0.021852,
            0.021673,
            0.021725,
            0.0217,
            0.021566,
            0.021667,
            0.021719,
            0.021662,
            0.021633,
            0.021651,
            0.021684,
            0.021631,
            0.021665,
            0.021668,
            0.021586,
            0.021555,
            0.021633,
            0.021632,
            0.021651,
            0.021617,
            0.021569,
            0.021581,
            0.02168,
            0.021515,
            0.021605,
            0.021547,
            0.021631,
            0.021578,
            0.021502,
            0.021582,
            0.02157,
            0.02157,
            0.02157,
            0.02157,
            0.021556,
            0.021552,
            0.021515,
            0.021567,
            0.021573,
            0.0215,
            0.021535,
            0.021536,
            0.021537,
            0.021654,
            0.021525,
        ],
        0,
        2777.0,
    ),
    (
        "pio8_high_speed",
        [
            0.020379,
            0.02036,
            0.02033,
            0.020425,
            0.020391,
            0.020232,
            0.02036,
            0.020346,
            0.020316,
            0.020314,
            0.020347,
            0.020294,
            0.020326,
            0.020229,
            0.020356,
            0.020314,
            0.020243,
            0.02032,
            0.020274,
            0.020183,
            0.020237,
            0.020221,
            0.020237,
            0.020287,
            0.020165,
            0.020246,
            0.020215,
            0.020254,
            0.020174,
            0.020168,
            0.020265,
            0.020164,
            0.020224,
            0.02011,
            0.020251,
            0.020188,
            0.020134,
            0.020169,
            0.020167,
            0.020137,
            0.020173,
            0.0202,
            0.020058,
            0.020138,
            0.020169,
            0.020155,
            0.020121,
            0.020056,
            0.02009,
        ],
        0,
        2965.2,
    ),
]


def replay(monkeypatch, intervals):
    calculator = RpmFromFrequency()
    monkeypatch.setattr(calculator, "turn_on_collection", lambda: setattr(calculator, "collecting", True))
    monkeypatch.setattr(calculator, "turn_off_collection", lambda: setattr(calculator, "collecting", False))

    def feed(_seconds):
        timestamp = 1_000_000_000
        calculator.callback(0, 0, 0, timestamp)
        for interval in intervals:
            timestamp += round(interval * 1_000_000_000)
            calculator.callback(0, 0, 0, timestamp)

    monkeypatch.setattr(calculator, "sleep_for", feed)
    raw = calculator.estimate(2.0)
    return calculator, raw


@pytest.mark.parametrize("name,intervals,adjustment,expected", TRACES, ids=[t[0] for t in TRACES])
def test_captured_trace_replay(monkeypatch, name, intervals, adjustment, expected) -> None:
    calculator, raw = replay(monkeypatch, intervals)
    assert raw == round(len(intervals) * 60 / sum(intervals), 1)
    correction = suggest_interval_correction(calculator.intervals_s)
    assert (correction.count_adjustment if correction else 0) == adjustment
    corrected = (len(intervals) + adjustment) * 60 / sum(intervals)
    assert corrected == pytest.approx(expected, abs=0.15)
    # Diagnostics must not mutate the captured events or the estimator aggregates.
    assert calculator._running_count == len(intervals)
    assert calculator.intervals_s == pytest.approx(intervals)


@pytest.mark.parametrize(
    "intervals",
    [
        [],
        [0.2] * 5,
        [0.2] * 5 + [0],
        [0.2] * 5 + [-0.2],
        [0.2] * 5 + [float("nan")],
        [0.2] * 5 + [float("inf")],
        [0.2] * 5 + [0.8],
        [0.2, 0.05, 0.15, 0.2, 0.05, 0.15, 0.2, 0.2, 0.2],
        [0.2] * 6 + [0.4, 0.4],
        [0.4] * 10,  # A whole window at half speed is not evidence of missed edges.
        [0.1, 0.12, 0.14, 0.16, 0.18, 0.2, 0.22, 0.24],
    ],
)
def test_abstains_on_insufficient_ambiguous_or_invalid_data(intervals) -> None:
    assert suggest_interval_correction(intervals) is None


def test_diagnostic_log_keeps_raw_rpm_and_reports_hypothesis(monkeypatch) -> None:
    intervals = TRACES[2][1]
    calculator, raw = replay(monkeypatch, intervals)
    job = SimpleNamespace(
        state=JobState.READY,
        currently_dodging_od=False,
        duty_cycle=17.0,
        target_rpm=300.0,
        _previous_rpm_observation=(300.0, 17.0),
        _last_rpm_anomaly_at=float("-inf"),
        rpm_calculator=calculator,
        measured_rpm=SimpleNamespace(timestamp=current_utc_datetime()),
        logger=MagicMock(),
    )
    Stirrer._log_rpm_anomaly(job, raw, 2.0, 17.0)
    payload = json.loads(job.logger.warning.call_args.args[0].split(": ", 1)[1])
    assert payload["rpm"] == payload["raw_rpm"] == raw
    assert payload["corrected_rpm"] == pytest.approx(298.9, abs=0.1)
    assert payload["correction_reason"] == "possible_extra_edge"
    assert payload["correction_interval_index"] == 6
    assert job._previous_rpm_observation == (raw, 17.0)

    # A bounded prefix must never be interpreted as the complete window.
    calculator._running_count += 1
    job._last_rpm_anomaly_at = float("-inf")
    Stirrer._log_rpm_anomaly(job, raw, 2.0, 17.0)
    payload = json.loads(job.logger.warning.call_args.args[0].split(": ", 1)[1])
    assert payload["intervals_truncated"]
    assert payload["correction_reason"] is None
    assert payload["corrected_rpm"] == raw


@pytest.mark.parametrize("trace_index", range(len(TRACES)))
def test_control_applies_only_extra_edge_correction(monkeypatch, trace_index) -> None:
    from .test_stirring_anomalies import make_stirrer

    calculator, raw = replay(monkeypatch, TRACES[trace_index][1])
    job = make_stirrer()
    object.__setattr__(job, "rpm_calculator", calculator)
    object.__setattr__(job, "_previous_rpm_observation", (raw, job.duty_cycle))
    object.__setattr__(job, "_last_rpm_anomaly_at", float("-inf"))
    monkeypatch.setattr(calculator, "estimate", lambda _: raw)
    object.__setattr__(job, "update_dc_with_measured_rpm", MagicMock())
    job.poll_and_update_dc(2.0)
    adjustment = TRACES[trace_index][2]
    expected = (
        round((len(calculator.intervals_s) - 1) * 60 / calculator._running_sum, 1)
        if adjustment == -1
        else raw
    )
    job.update_dc_with_measured_rpm.assert_called_once_with(expected)
    assert job.measured_rpm.measured_rpm == expected
    if adjustment:
        payload = json.loads(job.logger.warning.call_args.args[0].split(": ", 1)[1])
        assert payload["raw_rpm"] == raw
        assert payload["rpm"] == expected
        assert payload["correction_applied"] == (adjustment == -1)


def test_truncated_window_never_changes_feedback(monkeypatch) -> None:
    from .test_stirring_anomalies import make_stirrer

    # A split in the retained prefix is insufficient evidence about the full window.
    intervals = TRACES[0][1] + [0.2] * 130
    calculator, raw = replay(monkeypatch, intervals)
    assert len(calculator.intervals_s) == 128
    job = make_stirrer()
    object.__setattr__(job, "rpm_calculator", calculator)
    monkeypatch.setattr(calculator, "estimate", lambda _: raw)
    object.__setattr__(job, "update_dc_with_measured_rpm", MagicMock())
    job.poll_and_update_dc(30.0)
    job.update_dc_with_measured_rpm.assert_called_once_with(raw)
