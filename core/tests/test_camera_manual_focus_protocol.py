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
    focus_scores = iter([1000, 1050])

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        return {"focus_score": next(focus_scores)}

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
    assert take_snapshot_step.metadata["dialog"] == {
        "max_width": "md",
        "height": "min(90vh, 860px)",
    }

    first_focus_step = engine.advance({})

    assert first_focus_step.step_id == "focus_camera"
    assert first_focus_step.metadata["image"]["src"] == (
        f"/api/workers/unit-a/camera/focus_sessions/{session.session_id}/preview.jpg?v=1"
    )
    assert first_focus_step.metadata["actions"] == [
        {"label": "Take another snapshot", "inputs": {"action": "retake"}}
    ]
    assert first_focus_step.metadata["primary_action_label"] == "Focus is complete"
    assert first_focus_step.metadata["image"]["max_height"] == 520
    assert first_focus_step.metadata["image"]["aspect_ratio"] == "4 / 3"
    assert first_focus_step.metadata["dialog"] == {
        "max_width": "md",
        "height": "min(90vh, 860px)",
    }
    assert first_focus_step.metadata["guidance"] == {
        "title": "Focus guidance",
        "status": "initial",
        "message": "Adjust the focus slightly, then take another snapshot.",
    }

    second_focus_step = engine.advance({"action": "retake"})

    assert second_focus_step.metadata["image"]["src"].endswith("/preview.jpg?v=2")
    assert second_focus_step.metadata["image"]["caption"] == "Focus snapshot 2"
    assert second_focus_step.metadata["guidance"] == {
        "title": "Focus guidance",
        "status": "same",
        "message": "About the same — changes this small don't matter.",
    }
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


def test_manual_focus_coach_uses_a_five_percent_tolerance_around_the_hidden_peak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    focus_scores = iter([1000, 1050, 1103, 1048, 990, 1050])

    def executor(action: str, _payload: dict[str, object]) -> dict[str, object]:
        assert action == "camera_focus_capture"
        return {"focus_score": next(focus_scores)}

    session = start_manual_focus_session("camera")
    engine = SessionEngine(
        step_registry=with_terminal_steps(ManualCameraFocusProtocol.step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )

    steps = [
        engine.advance({}),
        engine.advance({"action": "retake"}),
        engine.advance({"action": "retake"}),
        engine.advance({"action": "retake"}),
        engine.advance({"action": "retake"}),
        engine.advance({"action": "retake"}),
    ]

    assert [step.metadata["guidance"]["status"] for step in steps] == [
        "initial",
        "same",
        "sharper",
        "same",
        "softer",
        "sharpest",
    ]
    assert steps[-1].metadata["guidance"]["message"] == (
        "You're in the sharpest range found. You can finish focusing."
    )

    assert session.data["best_focus_score"] == 1103
    assert "1103" not in str(engine.get_step())


def test_manual_focus_coach_falls_back_to_visual_guidance_without_a_focus_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")

    def executor(_action: str, _payload: dict[str, object]) -> dict[str, object]:
        return {"focus_score": None}

    session = start_manual_focus_session("camera")
    engine = SessionEngine(
        step_registry=with_terminal_steps(ManualCameraFocusProtocol.step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )

    step = engine.advance({})

    assert step.metadata["guidance"] == {
        "title": "Focus guidance",
        "status": "unavailable",
        "message": "Automatic focus guidance isn't available for this camera. Compare snapshots visually.",
    }


def test_manual_focus_session_completes_without_creating_a_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        if action == "camera_focus_capture":
            return {"focus_score": 1000}
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
            return {"focus_score": 1000}
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


def test_manual_focus_session_attempts_cleanup_when_snapshot_count_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(camera_manual_focus, "get_unit_name", lambda: "unit-a")
    calls: list[tuple[str, dict[str, object]]] = []

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((action, payload))
        return {"deleted": False}

    session = start_manual_focus_session("camera")

    ManualCameraFocusProtocol.on_session_abort(session, executor)

    assert session.data["snapshot_count"] == 0
    assert calls == [
        (
            "camera_focus_cleanup",
            {
                "unit": "unit-a",
                "session_id": session.session_id,
            },
        )
    ]


def test_manual_focus_protocol_is_registered() -> None:
    assert get_protocol("camera", "manual_focus") is ManualCameraFocusProtocol


def test_manual_focus_cli_reports_that_protocol_is_ui_only() -> None:
    with pytest.raises(click.UsageError, match="only available in the Pioreactor UI"):
        ManualCameraFocusProtocol().run("camera")
