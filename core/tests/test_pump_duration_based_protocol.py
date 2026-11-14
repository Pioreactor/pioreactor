# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import cast

import pytest
from pioreactor.calibrations.protocols import pump_duration_based
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils.job_manager import JobManager


def _make_context(data: dict[str, object] | None = None) -> SessionContext:
    session = CalibrationSession(
        session_id="session-1",
        protocol_name="pump",
        target_device="media_pump",
        status="in_progress",
        step_id="intro",
        data=data or {},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    return SessionContext(session=session, mode="cli", inputs=SessionInputs(None), collected_calibrations=[])


def test_get_execute_pump_for_device_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown pump device"):
        pump_duration_based._get_execute_pump_for_device(cast(PumpCalibrationDevices, "unknown"))


@pytest.mark.parametrize("pump_device", ["media_pump", "alt_media_pump", "waste_pump"])
@pytest.mark.parametrize(
    "running_job",
    [
        "dosing_automation",
        "add_media",
        "add_alt_media",
        "remove_waste",
    ],
)
def test_start_pump_session_rejects_conflicting_jobs(
    pump_device: PumpCalibrationDevices, running_job: str
) -> None:
    with JobManager() as job_manager:
        job_manager.register_and_set_running(
            unit="unit1",
            experiment="experiment",
            job_name=running_job,
            job_source="test",
            pid=12345,
            leader="leader",
            is_long_running_job=False,
        )

    with pytest.raises(ValueError, match=running_job):
        pump_duration_based.start_duration_based_session(pump_device)


@pytest.mark.parametrize("pump_device", ["media_pump", "alt_media_pump", "waste_pump"])
def test_start_pump_session_allows_stopped_pumps_and_unrelated_jobs(
    pump_device: PumpCalibrationDevices, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(pump_duration_based.config["PWM_reverse"], pump_device.removesuffix("_pump"), "4")
    with JobManager() as job_manager:
        pump_job_id = job_manager.register_and_set_running(
            unit="unit1",
            experiment="experiment",
            job_name="add_media",
            job_source="test",
            pid=12345,
            leader="leader",
            is_long_running_job=False,
        )
        job_manager.set_not_running(pump_job_id)
        job_manager.register_and_set_running(
            unit="unit1",
            experiment="experiment",
            job_name="stirring",
            job_source="test",
            pid=12346,
            leader="leader",
            is_long_running_job=False,
        )

    session = pump_duration_based.start_duration_based_session(pump_device)

    assert session.target_device == pump_device
    assert session.status == "in_progress"


def test_build_duration_chart_metadata_uses_min_length() -> None:
    ctx = _make_context({"durations_to_test": [1.0, 2.0, 3.0], "results": [0.5]})

    metadata = pump_duration_based._build_duration_chart_metadata(ctx)
    assert metadata is not None
    series = cast(list[dict[str, object]], metadata["series"])
    points = cast(list[dict[str, float]], series[0]["points"])
    assert points == [{"x": 1.0, "y": 0.5}]


def test_pump_actions_have_specific_primary_action_labels() -> None:
    assert (
        pump_duration_based.PrimePumpDuration().render(_make_context()).metadata["primary_action_label"]
        == "Prime pump"
    )
    assert (
        pump_duration_based.TracerRun()
        .render(_make_context({"tracer_duration_s": 1.0}))
        .metadata["primary_action_label"]
        == "Run pump"
    )
    assert (
        pump_duration_based.TestRun()
        .render(_make_context({"durations_to_test": [1.0], "test_index": 0, "results": []}))
        .metadata["primary_action_label"]
        == "Run pump"
    )


def test_volume_targets_stores_dose_range() -> None:
    ctx = _make_context()
    ctx.inputs = SessionInputs({"smallest_dose_ml": 0.5, "largest_dose_ml": 8.0})

    next_step = pump_duration_based.VolumeTargets().advance(ctx)

    assert isinstance(next_step, pump_duration_based.PwmSettings)
    assert ctx.data["smallest_dose_ml"] == 0.5
    assert ctx.data["largest_dose_ml"] == 8.0


def test_volume_targets_rejects_inverted_range() -> None:
    ctx = _make_context()
    ctx.inputs = SessionInputs({"smallest_dose_ml": 2.0, "largest_dose_ml": 1.0})

    with pytest.raises(ValueError, match="Largest dose"):
        pump_duration_based.VolumeTargets().advance(ctx)


def test_tracer_volume_spreads_durations_across_dose_range() -> None:
    ctx = _make_context({"smallest_dose_ml": 0.5, "largest_dose_ml": 8.0, "tracer_duration_s": 1.0})
    ctx.inputs = SessionInputs({"volume_ml": 1.0})

    pump_duration_based.TracerVolume().advance(ctx)

    min_duration = 0.5 * 0.8
    max_duration = 8.0 * 1.1
    assert ctx.data["durations_to_test"] == pytest.approx(
        [min_duration] * 4 + [(min_duration + max_duration) / 2] * 2 + [max_duration] * 4
    )
