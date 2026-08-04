# -*- coding: utf-8 -*-
import click
import pytest
from pioreactor.calibrations.protocols import camera_manual_focus
from pioreactor.calibrations.protocols.camera_manual_focus import ManualCameraFocusProtocol
from pioreactor.calibrations.protocols.camera_manual_focus import start_manual_focus_session
from pioreactor.calibrations.registry import get_protocol
from pioreactor.calibrations.session_flow import SessionEngine
from pioreactor.calibrations.session_flow import with_terminal_steps


def test_manual_focus_session_captures_and_retakes_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        return {"session_id": payload["session_id"]}

    session = start_manual_focus_session("camera")
    engine = SessionEngine(
        step_registry=with_terminal_steps(ManualCameraFocusProtocol.step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )

    take_snapshot_step = engine.get_step()
    assert take_snapshot_step.step_id == "take_snapshot"
    assert take_snapshot_step.metadata["primary_action_label"] == "Take snapshot"

    first_focus_step = engine.advance({})

    assert first_focus_step.step_id == "focus_camera"
    assert first_focus_step.metadata["image"]["src"] == (
        f"/api/workers/unit-a/camera/focus_sessions/{session.session_id}/preview.jpg?v=1"
    )
    assert first_focus_step.metadata["actions"] == [
        {"label": "Take another snapshot", "inputs": {"action": "retake"}}
    ]
    assert first_focus_step.metadata["primary_action_label"] == "Focus is complete"

    second_focus_step = engine.advance({"action": "retake"})

    assert second_focus_step.metadata["image"]["src"].endswith("/preview.jpg?v=2")
    assert second_focus_step.metadata["image"]["caption"] == "Focus snapshot 2"
    assert session.data["snapshot_count"] == 2
    assert calls == [
        (
            "camera_focus_capture",
            {"unit": "unit-a", "session_id": session.session_id},
        ),
        (
            "camera_focus_capture",
            {"unit": "unit-a", "session_id": session.session_id},
        ),
    ]


def test_manual_focus_session_completes_without_creating_a_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        if action == "camera_focus_capture":
            return {"session_id": payload["session_id"]}
        return {"deleted": True}

    session = start_manual_focus_session("camera")
    engine = SessionEngine(
        step_registry=with_terminal_steps(ManualCameraFocusProtocol.step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )
    engine.advance({})

    complete_step = engine.advance({})

    assert complete_step.step_id == "complete"
    assert session.status == "complete"
    assert session.result == {"title": "Camera focus complete"}
    assert engine.ctx.collected_calibrations == []
    assert session.data["snapshot_count"] == 1
    assert calls[-1] == (
        "camera_focus_cleanup",
        {
            "unit": "unit-a",
            "session_id": session.session_id,
        },
    )


def test_manual_focus_session_deletes_snapshots_when_aborted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        if action == "camera_focus_capture":
            return {"session_id": payload["session_id"]}
        return {"deleted": True}

    session = start_manual_focus_session("camera")
    engine = SessionEngine(
        step_registry=with_terminal_steps(ManualCameraFocusProtocol.step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )
    engine.advance({})

    ManualCameraFocusProtocol.on_session_abort(session, executor)

    assert session.data["snapshot_count"] == 1
    assert calls[-1] == (
        "camera_focus_cleanup",
        {
            "unit": "unit-a",
            "session_id": session.session_id,
        },
    )


def test_manual_focus_protocol_is_registered() -> None:
    assert get_protocol("camera", "manual_focus") is ManualCameraFocusProtocol


def test_manual_focus_cli_reports_that_protocol_is_ui_only() -> None:
    with pytest.raises(click.UsageError, match="only available in the Pioreactor UI"):
        ManualCameraFocusProtocol().run("camera")
