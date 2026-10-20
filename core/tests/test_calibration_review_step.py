# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import pytest
from pioreactor.calibrations.protocols import od_fusion_offset
from pioreactor.calibrations.protocols import od_fusion_standards
from pioreactor.calibrations.protocols import od_standards
from pioreactor.calibrations.protocols import pump_duration_based
from pioreactor.calibrations.protocols import stirring_dc_based
from pioreactor.calibrations.review import column
from pioreactor.calibrations.review import REVIEW_TABLE_FIELD
from pioreactor.calibrations.session_flow import advance_session
from pioreactor.calibrations.session_flow import get_session_step
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.whoami import get_testing_experiment_name


class FakeExecutor:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def __call__(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "read_aux_voltage":
            return {"voltage": 5.0}
        if action in ("save_calibration", "save_estimator"):
            self.saved.append(payload)
            return {"path": f"/tmp/{payload['device']}.yaml"}
        raise AssertionError(f"Unexpected action {action}")


def _session(protocol_name: str, target_device: str, data: dict[str, Any]) -> CalibrationSession:
    return CalibrationSession(
        session_id="session-review",
        protocol_name=protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="review_data",
        data=data,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _table(step: CalibrationStep) -> list[dict[str, Any]]:
    (field,) = step.fields
    assert field.field_type == "data_table"
    return [dict(row) for row in field.default]


def _od_session() -> CalibrationSession:
    return _session(
        od_standards.StandardsODProtocol.protocol_name,
        "od90",
        {
            "experiment": get_testing_experiment_name(),
            "calibration_name": "od-review-test",
            "channel_angle_map": {"2": "90"},
            "od600_values": [0.5, 1.0, 1.5, 0.0],
            "voltages_by_channel": {"2": [0.05, 0.1, 0.9, 0.001]},
        },
    )


def test_data_table_inputs_parse_editable_columns_and_include_flags() -> None:
    columns = [column("run", "Run"), column("volume", "Volume (mL)", editable=True, minimum=0.0001)]
    inputs = SessionInputs(
        {"table": [{"run": 1, "volume": "1.5", "include": True}, {"run": 2, "volume": 2, "include": False}]}
    )

    assert inputs.data_table("table", columns) == [
        {"volume": 1.5, "include": True},
        {"volume": 2.0, "include": False},
    ]


@pytest.mark.parametrize(
    "row, message",
    [
        ({"volume": ""}, "Row 1: 'Volume \\(mL\\)' is missing"),
        ({"volume": "abc"}, "Row 1: 'Volume \\(mL\\)' must be a number"),
        ({"volume": 0}, "Row 1: 'Volume \\(mL\\)' must be >= 0.0001"),
    ],
)
def test_data_table_inputs_reject_invalid_cells(row: dict[str, Any], message: str) -> None:
    columns = [column("volume", "Volume (mL)", editable=True, minimum=0.0001)]
    with pytest.raises(ValueError, match=message):
        SessionInputs({"table": [row]}).data_table("table", columns)


def test_od_standards_review_lists_every_point_with_the_blank_last() -> None:
    step = get_session_step(od_standards._OD_STANDARDS_STEPS, _od_session(), FakeExecutor())

    assert step.metadata["primary_action_label"] == "Save calibration"
    assert [row["standard"] for row in _table(step)] == ["1", "2", "3", "Blank"]
    assert all(row["include"] for row in _table(step))
    series = step.metadata["chart"]["series"][0]
    assert series["curve"]["type"] == "spline"


def test_od_standards_preview_applies_edits_without_saving() -> None:
    executor = FakeExecutor()
    session = _od_session()
    rows = _table(get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor))
    rows[2]["od600"] = 2.0
    rows[1]["include"] = False

    session = advance_session(
        od_standards._OD_STANDARDS_STEPS,
        session,
        {REVIEW_TABLE_FIELD: rows, "action": "preview"},
        executor,
    )

    assert session.status == "in_progress"
    assert session.step_id == "review_data"
    assert executor.saved == []
    rerendered = _table(get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor))
    assert rerendered[2]["od600"] == 2.0
    assert rerendered[1]["include"] is False
    chart_points = get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor).metadata["chart"][
        "series"
    ][0]["points"]
    assert [point["x"] for point in chart_points] == [0.5, 2.0, 0.0]


def test_od_standards_save_fits_only_included_points_with_corrected_values() -> None:
    executor = FakeExecutor()
    session = _od_session()
    rows = _table(get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor))
    rows[2]["od600"] = 2.0
    rows[1]["include"] = False

    session = advance_session(od_standards._OD_STANDARDS_STEPS, session, {REVIEW_TABLE_FIELD: rows}, executor)

    assert session.status == "complete"
    (saved,) = executor.saved
    assert saved["device"] == "od90"
    assert saved["calibration"]["recorded_data"] == {"x": [0.5, 2.0, 0.0], "y": [0.05, 0.9, 0.001]}


def test_review_requires_enough_included_rows() -> None:
    executor = FakeExecutor()
    session = _od_session()
    rows = _table(get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor))
    for row in rows[1:]:
        row["include"] = False

    with pytest.raises(ValueError, match="Keep at least 2 rows"):
        advance_session(od_standards._OD_STANDARDS_STEPS, session, {REVIEW_TABLE_FIELD: rows}, executor)
    assert executor.saved == []


def test_review_rejects_a_table_with_the_wrong_number_of_rows() -> None:
    executor = FakeExecutor()
    session = _od_session()
    rows = _table(get_session_step(od_standards._OD_STANDARDS_STEPS, session, executor))

    with pytest.raises(ValueError, match="recorded data changed"):
        advance_session(od_standards._OD_STANDARDS_STEPS, session, {REVIEW_TABLE_FIELD: rows[:-1]}, executor)


def _pump_session() -> CalibrationSession:
    return _session(
        pump_duration_based.DurationBasedPumpProtocol.protocol_name,
        "media_pump",
        {
            "calibration_name": "pump-review-test",
            "hz": 250.0,
            "dc": 100.0,
            "min_duration": 1.0,
            "max_duration": 3.0,
            "durations_to_test": [1.0, 1.0, 2.0, 3.0, 3.0],
            "results": [0.5, 0.5, 1.0, 15.0, 1.5],
        },
    )


def test_pump_review_corrects_a_mistyped_volume_before_saving() -> None:
    executor = FakeExecutor()
    session = _pump_session()
    step = get_session_step(pump_duration_based._PUMP_DURATION_STEPS, session, executor)
    rows = _table(step)
    assert [row["duration"] for row in rows] == [1.0, 1.0, 2.0, 3.0, 3.0]
    assert "chart" not in step.metadata
    assert step.metadata["actions"][0]["label"] == "Recalculate fit"
    assert step.metadata["summary"].startswith("Current fit")
    rows[3]["volume"] = 1.5

    session = advance_session(
        pump_duration_based._PUMP_DURATION_STEPS, session, {REVIEW_TABLE_FIELD: rows}, executor
    )

    assert session.status == "complete"
    (saved,) = executor.saved
    assert saved["calibration"]["recorded_data"]["y"] == [0.5, 0.5, 1.0, 1.5, 1.5]
    assert session.result is not None
    assert session.result["stats"]["slope"] == pytest.approx(0.5)


def test_pump_review_needs_two_distinct_durations() -> None:
    executor = FakeExecutor()
    session = _pump_session()
    rows = _table(get_session_step(pump_duration_based._PUMP_DURATION_STEPS, session, executor))
    for row in rows[2:]:
        row["include"] = False

    with pytest.raises(ValueError, match="two different durations"):
        advance_session(
            pump_duration_based._PUMP_DURATION_STEPS, session, {REVIEW_TABLE_FIELD: rows}, executor
        )


def test_stirring_review_drops_excluded_readings() -> None:
    executor = FakeExecutor()
    session = _session(
        stirring_dc_based.DCBasedStirringProtocol.protocol_name,
        "stirring",
        {"dcs": [20.0, 30.0, 40.0, 50.0], "rpms": [0.5, 300.0, 500.0, 700.0], "voltage": 5.0},
    )
    rows = _table(get_session_step(stirring_dc_based._DC_BASED_STEPS, session, executor))
    rows[0]["include"] = False

    session = advance_session(
        stirring_dc_based._DC_BASED_STEPS, session, {REVIEW_TABLE_FIELD: rows}, executor
    )

    assert session.status == "complete"
    (saved,) = executor.saved
    assert saved["calibration"]["recorded_data"] == {"x": [30.0, 40.0, 50.0], "y": [300.0, 500.0, 700.0]}


def test_fusion_standards_review_rebuilds_records_from_corrected_ods() -> None:
    standards = [
        {"index": 1, "od_value": 0.1, "readings": [["45", 0.01], ["90", 0.02], ["135", 0.03]]},
        {"index": 2, "od_value": 0.5, "readings": [["45", 0.05], ["90", 0.1], ["135", 0.15]]},
    ]
    session = _session(
        od_fusion_standards.FusionStandardsODProtocol.protocol_name,
        "od_fused",
        {"standards": standards, "estimator_name": "fused-test"},
    )
    step = get_session_step(od_fusion_standards._FUSION_STEPS, session, FakeExecutor())
    rows = _table(step)
    assert rows[1]["mean_90"] == pytest.approx(0.1)

    rows[1]["od600"] = 1.0
    session = advance_session(
        od_fusion_standards._FUSION_STEPS,
        session,
        {REVIEW_TABLE_FIELD: rows, "action": "preview"},
        FakeExecutor(),
    )
    assert session.data["standards"][1]["od_value"] == 1.0
    records = od_fusion_standards._records_from_standards(session.data["standards"])
    assert records[3][1] == pytest.approx(0.0)  # log10(1.0)


def test_fusion_offset_review_edits_standards_without_exclusion() -> None:
    session = _session(
        od_fusion_offset.FusionOffsetODProtocol.protocol_name,
        "od_fused",
        {
            "standards": [
                {"standard_od": 0.2, "estimated_od": 0.25},
                {"standard_od": 1.0, "estimated_od": 1.1},
            ]
        },
    )
    step = get_session_step(od_fusion_offset._FUSION_OFFSET_STEPS, session, FakeExecutor())
    rows = _table(step)
    assert "include" not in rows[0]
    assert "actions" not in step.metadata
    assert step.metadata["primary_action_label"] == "Save estimator"

    rows[1]["standard_od"] = 2.0
    session = advance_session(
        od_fusion_offset._FUSION_OFFSET_STEPS,
        session,
        {REVIEW_TABLE_FIELD: rows, "action": "preview"},
        FakeExecutor(),
    )
    assert session.data["standards"][1]["standard_od"] == 2.0


def test_cli_accepts_review_rows_as_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_prompt(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("The CLI must not prompt on a review step")

    monkeypatch.setattr("pioreactor.calibrations.session_flow.click.prompt", fail_prompt)
    session = _session(
        stirring_dc_based.DCBasedStirringProtocol.protocol_name,
        "stirring",
        {"dcs": [20.0, 30.0, 40.0], "rpms": [200.0, 300.0, 400.0], "voltage": 5.0},
    )
    registry: StepRegistry = stirring_dc_based._DC_BASED_STEPS

    (calibration,) = run_session_in_cli(registry, session)

    assert calibration.recorded_data == {"x": [20.0, 30.0, 40.0], "y": [200.0, 300.0, 400.0]}


def test_pump_dispense_steps_show_run_progress() -> None:
    session = _pump_session()
    session.step_id = "test_run"
    session.data["results"] = [0.5, 0.5]
    session.data["test_index"] = 2

    step = get_session_step(pump_duration_based._PUMP_DURATION_STEPS, session, FakeExecutor())

    assert step.title == "Dispense (run 3 of 5)"
