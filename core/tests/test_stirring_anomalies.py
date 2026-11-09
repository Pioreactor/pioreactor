# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from threading import RLock
from unittest.mock import Mock

import pytest
from pioreactor.background_jobs import stirring
from pioreactor.states import JobState
from pioreactor.structs import MeasuredRPM
from pioreactor.utils.timing import current_utc_datetime


def make_stirrer() -> stirring.Stirrer:
    job = stirring.Stirrer.__new__(stirring.Stirrer)
    for name, value in {
        "published_settings": {},
        "state": JobState.READY,
        "currently_dodging_od": False,
        "duty_cycle": 20.0,
        "target_rpm": 300.0,
        "rpm_calculator": stirring.RpmFromFrequency(),
        "logger": Mock(),
        "measured_rpm": MeasuredRPM(timestamp=current_utc_datetime(), measured_rpm=300),
    }.items():
        object.__setattr__(job, name, value)
    return job


def collect_edges(calculator: stirring.RpmFromFrequency, edges_s: list[float]) -> None:
    calculator.clear_aggregates()
    calculator.collecting = True
    for edge in edges_s:
        calculator.callback(0, 0, 0, round(edge * 1_000_000_000))
    calculator.collecting = False


def test_hall_diagnostics_are_bounded_and_do_not_change_rpm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calculator = stirring.RpmFromFrequency()
    monkeypatch.setattr(calculator, "turn_on_collection", lambda: setattr(calculator, "collecting", True))
    monkeypatch.setattr(calculator, "turn_off_collection", lambda: setattr(calculator, "collecting", False))
    edges = [i * 0.2 for i in range(201)]
    monkeypatch.setattr(calculator, "sleep_for", lambda _: collect_edges(calculator, edges))
    assert calculator.estimate(40) == 300.0
    assert calculator._running_count == 200
    assert len(calculator.intervals_s) == 128
    assert calculator.first_edge_timestamp_ns == 0
    assert calculator.last_edge_timestamp_ns == 40_000_000_000
    calculator.clear_aggregates()
    assert calculator.intervals_s == []
    assert calculator.first_edge_timestamp_ns is None


def test_smooth_rpm_jump_is_reported_and_control_still_receives_it() -> None:
    job = make_stirrer()
    calculator = job.rpm_calculator
    assert isinstance(calculator, stirring.RpmFromFrequency)
    collect_edges(calculator, [i * 0.12 for i in range(16)])
    job._log_rpm_anomaly(300, 2, 20)
    object.__setattr__(calculator, "estimate", Mock(return_value=500.0))
    object.__setattr__(job, "update_dc_with_measured_rpm", Mock())
    job.poll_and_update_dc(2)
    job.update_dc_with_measured_rpm.assert_called_once_with(500.0)
    payload = json.loads(job.logger.warning.call_args.args[0].split(": ", 1)[1])
    assert payload["reasons"] == ["abrupt_rpm_change"]
    assert payload["rpm"] == 500
    assert payload["previous_rpm"] == 300
    assert payload["interval_count"] == 15
    assert len(payload["intervals_s"]) == 15
    assert payload["intervals_truncated"] is False


def test_extra_hall_edge_is_detected_without_large_average_rpm_change() -> None:
    job = make_stirrer()
    calculator = job.rpm_calculator
    assert isinstance(calculator, stirring.RpmFromFrequency)
    job._log_rpm_anomaly(300, 2, 20)
    collect_edges(calculator, [0, 0.2, 0.4, 0.401, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8])
    job._log_rpm_anomaly(333.3, 2, 20)
    payload = json.loads(job.logger.warning.call_args.args[0].split(": ", 1)[1])
    assert payload["reasons"] == ["irregular_hall_intervals"]
    assert payload["min_interval_s"] == pytest.approx(0.001)
    assert payload["intervals_s"][2] == 0.001


@pytest.mark.parametrize(
    "case", ["startup", "dodging", "sleeping", "target_change", "duty_change", "during_sample"]
)
def test_expected_transitions_do_not_warn(case: str) -> None:
    job = make_stirrer()
    if case != "startup":
        job._log_rpm_anomaly(300, 2, 20)
    if case == "dodging":
        object.__setattr__(job, "currently_dodging_od", True)
    elif case == "sleeping":
        object.__setattr__(job, "state", JobState.SLEEPING)
    elif case == "target_change":
        object.__setattr__(job, "pid", Mock())
        object.__setattr__(job, "duty_cycle_estimate_for", Mock(return_value=20.0))
        job.update_target_rpm(500)
    elif case == "duty_change":
        object.__setattr__(job, "duty_cycle", 30)
    job._log_rpm_anomaly(500, 2, 19 if case == "during_sample" else job.duty_cycle)
    job.logger.warning.assert_not_called()


def test_normal_variation_and_zero_rpm_do_not_duplicate_existing_warning() -> None:
    job = make_stirrer()
    for rpm in [300, 310, 290, 305, 0]:
        job._log_rpm_anomaly(rpm, 2, 20)
    job.logger.warning.assert_not_called()


def test_anomaly_warnings_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    job = make_stirrer()
    now = [100.0]
    monkeypatch.setattr(stirring, "monotonic", lambda: now[0])
    for rpm in [300, 500, 300, 500]:
        job._log_rpm_anomaly(rpm, 2, 20)
    assert job.logger.warning.call_count == 1
    now[0] += 60
    job._log_rpm_anomaly(300, 2, 20)
    assert job.logger.warning.call_count == 2


@pytest.mark.parametrize(
    "target, calibrated_duty, ramp, subsequent_outlier",
    [(900.0, 40.0, [350, 500, 700, 890, 900], 500), (100.0, 10.0, [280, 180, 130, 105, 100], 300)],
)
def test_manual_target_change_suppresses_entire_ramp_then_rearms(
    target: float, calibrated_duty: float, ramp: list[float], subsequent_outlier: float
) -> None:
    job = make_stirrer()
    job._log_rpm_anomaly(300, 2, 20)
    object.__setattr__(job, "duty_cycle_lock", RLock())
    object.__setattr__(job, "pid", Mock())
    object.__setattr__(job, "duty_cycle_estimate_for", Mock(return_value=calibrated_duty))
    object.__setattr__(
        job, "apply_duty_cycle", Mock(side_effect=lambda dc: object.__setattr__(job, "duty_cycle", dc))
    )
    job.set_target_rpm(target)
    job.apply_duty_cycle.assert_called_once_with(calibrated_duty)
    for rpm in ramp:
        job._log_rpm_anomaly(rpm, 2, calibrated_duty)
    job.logger.warning.assert_not_called()
    job._log_rpm_anomaly(subsequent_outlier, 2, calibrated_duty)
    job.logger.warning.assert_called_once()
